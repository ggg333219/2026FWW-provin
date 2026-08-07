package main

import (
    "context"
    "fmt"
    "time"

    svc "smart-teaching-backend/internal/service"
)

func main() {
    client := svc.NewAIEngineClient("http://127.0.0.1:8000", 30*time.Second)
    req := &svc.ParseProcessRequest{
        SessionID: "go_integration_test",
        FilePaths: []string{"ai_engine/uploads/test_dummy.pdf"},
    }
    ctx := context.Background()
    resp, err := client.ParseProcess(ctx, req)
    if err != nil {
        fmt.Printf("ParseProcess error: %v\n", err)
        return
    }
    fmt.Printf("ParseProcess OK: task_id=%s status=%s assets=%d\n", resp.TaskID, resp.Status, len(resp.Assets))
}
