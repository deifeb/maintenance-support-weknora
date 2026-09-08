from pydantic import BaseModel


class AIConfirmationApproveRequest(BaseModel):
    confirmation_token: str
    expected_input_digest: str
    comment: str | None = None


class AIConfirmationRejectRequest(BaseModel):
    comment: str | None = None
