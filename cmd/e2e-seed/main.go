package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

const passwordEnvironmentKey = "E2E_TEST_PASSWORD"

type Actor struct {
	Role   string `json:"role"`
	Tenant string `json:"tenant"`
}

type actorManifest struct {
	Actors map[string]Actor `json:"actors"`
}

type seedFlags struct {
	databaseURL  string
	manifestPath string
}

var requiredActors = []struct {
	alias string
	role  string
	email string
}{
	{alias: "tenant-a-admin", role: "ADMIN", email: "tenant-a-admin@example.test"},
	{alias: "tenant-b-admin", role: "ADMIN", email: "tenant-b-admin@example.test"},
	{alias: "tenant-a-viewer", role: "VIEWER", email: "tenant-a-viewer@example.test"},
	{alias: "tenant-a-contributor", role: "CONTRIBUTOR", email: "tenant-a-contributor@example.test"},
}

func validateActors(actors map[string]Actor) error {
	for _, required := range requiredActors {
		actor, ok := actors[required.alias]
		if !ok {
			return fmt.Errorf("missing actor %s", required.alias)
		}
		if actor.Role != required.role {
			return fmt.Errorf("actor %s has role %q, want %q", required.alias, actor.Role, required.role)
		}
	}
	if len(actors) != len(requiredActors) {
		return fmt.Errorf("expected exactly %d actors", len(requiredActors))
	}
	return nil
}

func parseFlags(args []string) (seedFlags, error) {
	flags := flag.NewFlagSet("e2e-seed", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	databaseURL := flags.String("database-url", "", "private runtime database URL")
	manifestPath := flags.String("manifest-path", "", "runtime actor manifest path")
	if err := flags.Parse(args); err != nil {
		return seedFlags{}, err
	}
	if len(flags.Args()) != 0 {
		return seedFlags{}, errors.New("unexpected positional arguments")
	}
	if strings.TrimSpace(*databaseURL) == "" || strings.TrimSpace(*manifestPath) == "" {
		return seedFlags{}, errors.New("--database-url and --manifest-path are required")
	}
	return seedFlags{databaseURL: *databaseURL, manifestPath: *manifestPath}, nil
}

func main() {
	flags, err := parseFlags(os.Args[1:])
	if err != nil {
		panic(err)
	}
	if err := seed(flags.databaseURL, flags.manifestPath, os.Getenv(passwordEnvironmentKey)); err != nil {
		panic(err)
	}
}

func seed(databaseURL, manifestPath, password string) error {
	if strings.TrimSpace(password) == "" {
		return errors.New("E2E_TEST_PASSWORD is required")
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return fmt.Errorf("hash e2e password: %w", err)
	}
	db, err := gorm.Open(postgres.Open(databaseURL), &gorm.Config{})
	if err != nil {
		return fmt.Errorf("open e2e database: %w", err)
	}
	success := false
	defer func() {
		if sqlDB, closeErr := db.DB(); closeErr == nil && !success {
			_ = sqlDB.Close()
		}
	}()

	manifest := actorManifest{Actors: make(map[string]Actor, len(requiredActors))}
	err = db.Transaction(func(tx *gorm.DB) error {
		tenantIDs := make(map[string]uint64, 2)
		for _, tenant := range []struct {
			alias string
			name  string
		}{
			{alias: "tenant-a", name: "Maintenance E2E Tenant A"},
			{alias: "tenant-b", name: "Maintenance E2E Tenant B"},
		} {
			id, tenantErr := getOrCreateTenant(tx, tenant.name)
			if tenantErr != nil {
				return tenantErr
			}
			tenantIDs[tenant.alias] = id
		}

		for _, required := range requiredActors {
			tenantAlias := "tenant-a"
			if required.alias == "tenant-b-admin" {
				tenantAlias = "tenant-b"
			}
			username := strings.ReplaceAll(required.alias, "-", "_")
			user, userErr := getOrCreateUser(tx, required.email, username, tenantIDs[tenantAlias], string(hash))
			if userErr != nil {
				return userErr
			}
			if memberErr := getOrCreateMembership(tx, user.ID, tenantIDs[tenantAlias], strings.ToLower(required.role)); memberErr != nil {
				return memberErr
			}
			manifest.Actors[required.alias] = Actor{
				Role: required.role, Tenant: strconv.FormatUint(tenantIDs[tenantAlias], 10),
			}
		}
		return validateActors(manifest.Actors)
	})
	if err != nil {
		return err
	}
	if err := writeManifest(manifestPath, manifest); err != nil {
		return err
	}
	success = true
	if sqlDB, closeErr := db.DB(); closeErr == nil {
		_ = sqlDB.Close()
	}
	return nil
}

func getOrCreateTenant(db *gorm.DB, name string) (uint64, error) {
	var id uint64
	if err := db.Raw("SELECT id FROM tenants WHERE name = ? ORDER BY id LIMIT 1", name).Scan(&id).Error; err != nil {
		return 0, fmt.Errorf("find tenant: %w", err)
	}
	if id != 0 {
		return id, nil
	}
	row := map[string]any{
		"name":              name,
		"description":       "Disposable maintenance E2E tenant",
		"status":            "active",
		"business":          "maintenance-e2e",
		"api_key":           "",
		"retriever_engines": "[]",
	}
	if err := db.Table("tenants").Create(row).Error; err != nil {
		return 0, fmt.Errorf("create tenant: %w", err)
	}
	if err := db.Raw("SELECT id FROM tenants WHERE name = ? ORDER BY id DESC LIMIT 1", name).Scan(&id).Error; err != nil || id == 0 {
		if err == nil {
			err = errors.New("created tenant has no id")
		}
		return 0, fmt.Errorf("read created tenant: %w", err)
	}
	return id, nil
}

func getOrCreateUser(db *gorm.DB, email, username string, tenantID uint64, passwordHash string) (types.User, error) {
	var user types.User
	err := db.Where("email = ?", email).First(&user).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		user = types.User{ID: uuid.NewString(), Username: username, Email: email, PasswordHash: passwordHash, TenantID: tenantID, IsActive: true}
		if err := db.Create(&user).Error; err != nil {
			return types.User{}, fmt.Errorf("create user: %w", err)
		}
		return user, nil
	}
	if err != nil {
		return types.User{}, fmt.Errorf("find user: %w", err)
	}
	if err := db.Model(&user).Updates(map[string]any{"username": username, "password_hash": passwordHash, "tenant_id": tenantID, "is_active": true, "deleted_at": nil}).Error; err != nil {
		return types.User{}, fmt.Errorf("refresh user: %w", err)
	}
	return user, nil
}

func getOrCreateMembership(db *gorm.DB, userID string, tenantID uint64, role string) error {
	var member types.TenantMember
	err := db.Where("user_id = ? AND tenant_id = ?", userID, tenantID).First(&member).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		if err := db.Create(&types.TenantMember{UserID: userID, TenantID: tenantID, Role: types.TenantRole(role), Status: types.TenantMemberStatusActive}).Error; err != nil {
			return fmt.Errorf("create membership: %w", err)
		}
		return nil
	}
	if err != nil {
		return fmt.Errorf("find membership: %w", err)
	}
	return db.Model(&member).Updates(map[string]any{"role": role, "status": "active", "deleted_at": nil}).Error
}

func writeManifest(path string, manifest actorManifest) error {
	if err := validateActors(manifest.Actors); err != nil {
		return err
	}
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return fmt.Errorf("encode actor manifest: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("create actor manifest directory: %w", err)
	}
	if err := os.WriteFile(path, append(data, '\n'), 0o600); err != nil {
		return fmt.Errorf("write actor manifest: %w", err)
	}
	return nil
}
