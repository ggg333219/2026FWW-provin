package service

import "context"

// InteractiveGenerateRequest is the gateway contract for generating the
// interactive material belonging to one generated node.
type InteractiveGenerateRequest struct {
	Node            map[string]any `json:"node"`
	InteractivePlan map[string]any `json:"interactive_plan,omitempty"`
}

type InteractiveGenerateResponse struct {
	Items []map[string]any `json:"items"`
}

// GenerateInteractive is intentionally kept out of the AIEngine interface so
// older test doubles and legacy clients remain source-compatible. The real
// HTTP client implements it and the handler checks for this capability.
func (c *aiEngineClient) GenerateInteractive(ctx context.Context, req InteractiveGenerateRequest) (*InteractiveGenerateResponse, error) {
	var result InteractiveGenerateResponse
	if err := c.postJSON(ctx, "/gen/interactive", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}
