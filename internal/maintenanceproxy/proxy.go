package maintenanceproxy

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

const (
	publicMaintenancePrefix = "/api/maintenance/"
	upstreamAPIPrefix       = "/api/"
	maxRequestIDBytes       = 128
)

var errInvalidUpstreamResponse = errors.New("invalid maintenance upstream response")

type ActorResolver func(*gin.Context) (Actor, error)

type Proxy struct {
	target  *url.URL
	reverse *httputil.ReverseProxy
	signer  *Signer
	resolve ActorResolver
}

type proxyRequestState struct {
	token         string
	requestID     string
	upstreamPath  string
	upstreamQuery string
}

type proxyRequestStateKey struct{}

type proxyErrorEnvelope struct {
	Success bool             `json:"success"`
	Error   proxyErrorDetail `json:"error"`
}

type proxyErrorDetail struct {
	Code    string            `json:"code"`
	Message string            `json:"message"`
	Details proxyErrorContext `json:"details"`
}

type proxyErrorContext struct {
	RequestID string `json:"request_id"`
}

func New(baseURL string, signer *Signer, actorResolver ActorResolver, responseHeaderTimeout time.Duration) (*Proxy, error) {
	if signer == nil {
		return nil, errors.New("maintenance proxy signer is required")
	}
	if actorResolver == nil {
		return nil, errors.New("maintenance proxy actor resolver is required")
	}
	if responseHeaderTimeout <= 0 {
		return nil, errors.New("maintenance proxy response header timeout must be positive")
	}

	target, err := parseMaintenanceTarget(baseURL)
	if err != nil {
		return nil, err
	}

	defaultTransport, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		return nil, errors.New("maintenance proxy default transport must be *http.Transport")
	}
	transport := defaultTransport.Clone()
	transport.Proxy = nil
	transport.ResponseHeaderTimeout = responseHeaderTimeout

	proxy := &Proxy{
		target:  target,
		signer:  signer,
		resolve: actorResolver,
	}
	proxy.reverse = &httputil.ReverseProxy{
		Transport:     transport,
		FlushInterval: 100 * time.Millisecond,
	}
	proxy.reverse.Rewrite = func(request *httputil.ProxyRequest) {
		state, ok := request.In.Context().Value(proxyRequestStateKey{}).(proxyRequestState)
		if !ok {
			request.Out.URL = &url.URL{}
			request.Out.Host = ""
			request.Out.Header = make(http.Header)
			return
		}

		request.SetURL(proxy.target)
		request.Out.URL.Path = state.upstreamPath
		request.Out.URL.RawPath = ""
		request.Out.URL.RawQuery = state.upstreamQuery

		sanitizeOutboundRequestHeaders(request.Out.Header)
		request.SetXForwarded()
		request.Out.Header.Set("Authorization", "Bearer "+state.token)
		request.Out.Header.Set("X-Request-ID", state.requestID)
	}
	proxy.reverse.ModifyResponse = proxy.modifyResponse
	proxy.reverse.ErrorHandler = proxy.handleProxyError
	return proxy, nil
}

func parseMaintenanceTarget(raw string) (*url.URL, error) {
	target, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !target.IsAbs() || target.Hostname() == "" {
		return nil, errors.New("maintenance proxy base URL must be an absolute HTTP(S) URL")
	}
	if target.Scheme != "http" && target.Scheme != "https" {
		return nil, errors.New("maintenance proxy base URL must use http or https")
	}
	if target.User != nil {
		return nil, errors.New("maintenance proxy base URL must not contain userinfo")
	}
	if target.RawQuery != "" || target.ForceQuery {
		return nil, errors.New("maintenance proxy base URL must not contain a query")
	}
	if target.Fragment != "" {
		return nil, errors.New("maintenance proxy base URL must not contain a fragment")
	}
	if target.Path != "" && target.Path != "/" {
		return nil, errors.New("maintenance proxy base URL must identify the service root")
	}
	if target.RawPath != "" && target.RawPath != "/" {
		return nil, errors.New("maintenance proxy base URL must identify the service root")
	}
	target.Path = ""
	target.RawPath = ""
	return target, nil
}

var allowedProxyMethods = map[string]struct{}{
	http.MethodGet:     {},
	http.MethodHead:    {},
	http.MethodPost:    {},
	http.MethodPut:     {},
	http.MethodPatch:   {},
	http.MethodDelete:  {},
	http.MethodOptions: {},
}

func validateProxyMethod(method string) bool {
	_, ok := allowedProxyMethods[method]
	return ok
}

func hasProtocolUpgrade(request *http.Request) bool {
	if strings.TrimSpace(request.Header.Get("Upgrade")) != "" {
		return true
	}
	for _, value := range request.Header.Values("Connection") {
		for _, token := range strings.Split(value, ",") {
			if strings.EqualFold(strings.TrimSpace(token), "upgrade") {
				return true
			}
		}
	}
	return false
}

func normalizeProxyTarget(target *url.URL) (string, string, error) {
	if target == nil || !strings.HasPrefix(target.Path, publicMaintenancePrefix) {
		return "", "", errors.New("maintenance proxy path must start with /api/maintenance/")
	}
	if strings.Contains(target.Path, "//") || strings.Contains(target.Path, "\\") {
		return "", "", errors.New("maintenance proxy path contains an ambiguous separator")
	}
	for _, value := range target.Path {
		if value == 0 || value < 0x20 || value == 0x7f {
			return "", "", errors.New("maintenance proxy path contains a control character")
		}
	}
	for _, segment := range strings.Split(target.Path, "/") {
		if segment == "." || segment == ".." {
			return "", "", errors.New("maintenance proxy path contains a dot segment")
		}
	}

	escapedPath := strings.ToLower(target.EscapedPath())
	if target.RawPath != "" && target.RawPath != target.EscapedPath() {
		return "", "", errors.New("maintenance proxy raw path is inconsistent")
	}
	for _, encoded := range []string{"%2f", "%5c", "%2e", "%00"} {
		if strings.Contains(escapedPath, encoded) {
			return "", "", errors.New("maintenance proxy path contains an encoded separator or dot")
		}
	}

	suffix := strings.TrimPrefix(target.Path, publicMaintenancePrefix)
	upstreamPath := upstreamAPIPrefix + suffix
	if !strings.HasPrefix(upstreamPath, upstreamAPIPrefix) {
		return "", "", errors.New("maintenance proxy path rewrite escaped the API prefix")
	}

	values, err := url.ParseQuery(target.RawQuery)
	if err != nil {
		return "", "", errors.New("maintenance proxy query is invalid")
	}
	return upstreamPath, values.Encode(), nil
}

func normalizeTrustedRequestID(raw string) (string, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return "", errors.New("maintenance request ID is required")
	}
	if len([]byte(value)) > maxRequestIDBytes {
		return "", errors.New("maintenance request ID exceeds 128 bytes")
	}
	for _, char := range value {
		if char == '\r' || char == '\n' || char == 0 || char < 0x20 || char == 0x7f {
			return "", errors.New("maintenance request ID contains a control character")
		}
	}
	return value, nil
}

func newFallbackRequestID() string {
	requestID, err := newUUIDv4()
	if err != nil {
		return "maintenance-request-unavailable"
	}
	return requestID
}

func writeProxyError(writer http.ResponseWriter, status int, code, message, requestID string) {
	if normalized, err := normalizeTrustedRequestID(requestID); err == nil {
		requestID = normalized
	} else {
		requestID = newFallbackRequestID()
	}

	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
	writer.Header().Set("X-Request-ID", requestID)
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(proxyErrorEnvelope{
		Success: false,
		Error: proxyErrorDetail{
			Code:    code,
			Message: message,
			Details: proxyErrorContext{RequestID: requestID},
		},
	})
}

func (p *Proxy) ServeHTTP(c *gin.Context) {
	if p == nil || p.reverse == nil || p.signer == nil || p.resolve == nil {
		c.Abort()
		writeProxyError(c.Writer, http.StatusInternalServerError, "MAINTENANCE_IDENTITY_EXCHANGE_FAILED", "Maintenance identity exchange failed", "")
		return
	}
	if !validateProxyMethod(c.Request.Method) {
		c.Header("Allow", "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS")
		c.Abort()
		writeProxyError(c.Writer, http.StatusMethodNotAllowed, "MAINTENANCE_METHOD_NOT_ALLOWED", "HTTP method is not allowed", "")
		return
	}
	if hasProtocolUpgrade(c.Request) {
		c.Abort()
		writeProxyError(c.Writer, http.StatusBadRequest, "MAINTENANCE_PROTOCOL_UPGRADE_NOT_SUPPORTED", "Protocol upgrade is not supported", "")
		return
	}
	upstreamPath, upstreamQuery, err := normalizeProxyTarget(c.Request.URL)
	if err != nil {
		c.Abort()
		writeProxyError(c.Writer, http.StatusBadRequest, "MAINTENANCE_INVALID_PROXY_PATH", "Maintenance proxy path is invalid", "")
		return
	}

	actor, resolveErr := p.resolve(c)
	if resolveErr != nil {
		requestID, requestIDErr := normalizeTrustedRequestID(actor.RequestID)
		if requestIDErr != nil {
			requestID = newFallbackRequestID()
		}
		c.Abort()
		writeProxyError(c.Writer, http.StatusUnauthorized, "MAINTENANCE_ACTOR_UNAVAILABLE", "Maintenance actor is unavailable", requestID)
		return
	}

	requestID, err := normalizeTrustedRequestID(actor.RequestID)
	if err != nil {
		c.Abort()
		writeProxyError(c.Writer, http.StatusInternalServerError, "MAINTENANCE_IDENTITY_EXCHANGE_FAILED", "Maintenance identity exchange failed", "")
		return
	}
	actor.RequestID = requestID

	token, err := p.signer.Sign(actor)
	if err != nil {
		c.Abort()
		writeProxyError(c.Writer, http.StatusInternalServerError, "MAINTENANCE_IDENTITY_EXCHANGE_FAILED", "Maintenance identity exchange failed", requestID)
		return
	}

	state := proxyRequestState{
		token:         token,
		requestID:     requestID,
		upstreamPath:  upstreamPath,
		upstreamQuery: upstreamQuery,
	}
	request := c.Request.Clone(context.WithValue(c.Request.Context(), proxyRequestStateKey{}, state))
	p.reverse.ServeHTTP(c.Writer, request)
	c.Abort()
}

var blockedOutboundRequestHeaders = []string{
	"Authorization",
	"Cookie",
	"Proxy-Authorization",
	"X-Tenant-ID",
	"X-User-ID",
	"X-User-Roles",
	"X-Internal-Authorization",
	"Forwarded",
	"X-Forwarded-For",
	"X-Forwarded-Host",
	"X-Forwarded-Proto",
	"X-Forwarded-Port",
	"X-Real-IP",
}

func sanitizeOutboundRequestHeaders(header http.Header) {
	for _, name := range blockedOutboundRequestHeaders {
		header.Del(name)
	}
	deleteHeadersWithPrefixes(header, "x-internal-", "x-maintenance-")
}

func deleteHeadersWithPrefixes(header http.Header, prefixes ...string) {
	for name := range header {
		lower := strings.ToLower(name)
		for _, prefix := range prefixes {
			if strings.HasPrefix(lower, prefix) {
				header.Del(name)
				break
			}
		}
	}
}

var blockedUpstreamResponseHeaders = []string{
	"Set-Cookie",
	"Server",
	"Via",
	"X-Powered-By",
	"Alt-Svc",
	"Refresh",
}

func (p *Proxy) modifyResponse(response *http.Response) error {
	state, ok := response.Request.Context().Value(proxyRequestStateKey{}).(proxyRequestState)
	if !ok {
		_ = response.Body.Close()
		return fmt.Errorf("%w: missing request state", errInvalidUpstreamResponse)
	}

	for _, name := range blockedUpstreamResponseHeaders {
		response.Header.Del(name)
	}
	deleteHeadersWithPrefixes(response.Header, "x-internal-", "x-maintenance-")
	response.Header.Set("X-Request-ID", state.requestID)

	location := response.Header.Get("Location")
	if location == "" {
		return nil
	}
	rewritten, err := p.rewriteLocation(location)
	if err != nil {
		_ = response.Body.Close()
		return fmt.Errorf("%w: location rejected", errInvalidUpstreamResponse)
	}
	response.Header.Set("Location", rewritten)
	return nil
}

func (p *Proxy) rewriteLocation(raw string) (string, error) {
	location, err := url.Parse(raw)
	if err != nil || location.User != nil {
		return "", errInvalidUpstreamResponse
	}

	if location.IsAbs() {
		if !strings.EqualFold(location.Scheme, p.target.Scheme) || !strings.EqualFold(location.Host, p.target.Host) {
			return "", errInvalidUpstreamResponse
		}
	} else if location.Host != "" || location.Scheme != "" {
		return "", errInvalidUpstreamResponse
	}

	if !strings.HasPrefix(location.Path, upstreamAPIPrefix) {
		return "", errInvalidUpstreamResponse
	}
	if strings.Contains(location.Path, "//") || strings.Contains(location.Path, "\\") {
		return "", errInvalidUpstreamResponse
	}
	for _, segment := range strings.Split(location.Path, "/") {
		if segment == "." || segment == ".." {
			return "", errInvalidUpstreamResponse
		}
	}
	escaped := strings.ToLower(location.EscapedPath())
	for _, encoded := range []string{"%2f", "%5c", "%2e", "%00"} {
		if strings.Contains(escaped, encoded) {
			return "", errInvalidUpstreamResponse
		}
	}

	location.Scheme = ""
	location.Host = ""
	location.User = nil
	location.Path = publicMaintenancePrefix + strings.TrimPrefix(location.Path, upstreamAPIPrefix)
	location.RawPath = ""
	return location.String(), nil
}

func (p *Proxy) handleProxyError(writer http.ResponseWriter, request *http.Request, proxyErr error) {
	state, _ := request.Context().Value(proxyRequestStateKey{}).(proxyRequestState)
	if errors.Is(proxyErr, errInvalidUpstreamResponse) {
		writeProxyError(writer, http.StatusBadGateway, "MAINTENANCE_INVALID_UPSTREAM_RESPONSE", "Maintenance service returned an invalid response", state.requestID)
		return
	}
	writeProxyError(writer, http.StatusBadGateway, "MAINTENANCE_UPSTREAM_UNAVAILABLE", "Maintenance service is temporarily unavailable", state.requestID)
}
