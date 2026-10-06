package service

import "strings"

// ensureElementMetadata creates the stable semantic element layer for legacy
// node snapshots. It lives in metadata so old clients keep their DTO shape.
func ensureElementMetadata(nodes []TeachingNodeItem) []TeachingNodeItem {
	out := make([]TeachingNodeItem, len(nodes))
	copy(out, nodes)
	for i := range out {
		if out[i].Metadata == nil {
			out[i].Metadata = map[string]any{}
		}
		if elements, ok := out[i].Metadata["elements"].([]map[string]any); ok && len(elements) > 0 {
			continue
		}
		if raw, ok := out[i].Metadata["elements"].([]any); ok && len(raw) > 0 {
			elements := make([]map[string]any, 0, len(raw))
			for _, item := range raw {
				if element, ok := item.(map[string]any); ok {
					elements = append(elements, element)
				}
			}
			if len(elements) > 0 {
				out[i].Metadata["elements"] = elements
				continue
			}
		}
		elements := make([]map[string]any, 0, 3)
		if strings.TrimSpace(out[i].Title) != "" {
			elements = append(elements, newElement(out[i].NodeID, "title", "text", out[i].Title, "top"))
		}
		body := strings.TrimSpace(out[i].Content)
		if body == "" {
			body = strings.TrimSpace(out[i].Summary)
		}
		if body != "" {
			elements = append(elements, newElement(out[i].NodeID, "body", "text", body, "right"))
		}
		points := out[i].KeyPoints
		if len(points) == 0 {
			points = out[i].CorePoints
		}
		if len(points) > 0 {
			elements = append(elements, newElement(out[i].NodeID, "list", "text", points, "left"))
		}
		if out[i].Figure != nil {
			kind := "shape"
			if value, ok := out[i].Figure["kind"].(string); ok && value == "chart" {
				kind = "chart"
			}
			elements = append(elements, newElement(out[i].NodeID, kind, kind, out[i].Figure, "right"))
		}
		out[i].Metadata["elements"] = elements
	}
	return out
}

func newElement(nodeID, role, elementType string, content any, position string) map[string]any {
	return map[string]any{
		"element_id":        "el_" + nodeID + "_" + role,
		"page_id":           nodeID,
		"element_type":      elementType,
		"role":              role,
		"content":           content,
		"geometry":          map[string]any{"x": 0, "y": 0, "width": 0, "height": 0, "position": position},
		"style":             map[string]any{},
		"group_id":          nil,
		"source_refs":       []string{},
		"parent_element_id": nil,
	}
}

func syncElementContent(nodes []TeachingNodeItem) []TeachingNodeItem {
	out := make([]TeachingNodeItem, len(nodes))
	copy(out, nodes)
	for i := range out {
		elements, ok := out[i].Metadata["elements"].([]map[string]any)
		if !ok {
			continue
		}
		for _, element := range elements {
			switch element["role"] {
			case "title":
				element["content"] = out[i].Title
			case "body":
				if out[i].Content != "" {
					element["content"] = out[i].Content
				} else {
					element["content"] = out[i].Summary
				}
			case "list":
				if len(out[i].KeyPoints) > 0 {
					element["content"] = out[i].KeyPoints
				} else {
					element["content"] = out[i].CorePoints
				}
			}
		}
	}
	return out
}

func applyPresentationToNodes(nodes []TeachingNodeItem, presentation map[string]string) []TeachingNodeItem {
	if len(presentation) == 0 {
		return nodes
	}
	out := make([]TeachingNodeItem, len(nodes))
	copy(out, nodes)
	for i := range out {
		if out[i].Metadata == nil {
			out[i].Metadata = map[string]any{}
		}
		current := map[string]any{}
		if raw, ok := out[i].Metadata["presentation"].(map[string]any); ok {
			for key, value := range raw {
				current[key] = value
			}
		}
		for key, value := range presentation {
			current[key] = value
		}
		out[i].Metadata["presentation"] = current
	}
	return out
}
