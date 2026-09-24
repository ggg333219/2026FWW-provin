import sys, json
d = json.load(sys.stdin)
c = d.get('code')
m = d.get('message', '')
data = d.get('data', {})
print(f'code={c} message={m}')
print(f'script_len={len(data.get("content",""))}')
print(f'mindmap_len={len(data.get("mindmapMarkdown",""))}')
nodes = data.get('nodes', [])
if nodes:
    n = nodes[0]
    print(f'first_node: {n.get("node_id")} script_len={len(n.get("scriptText","") or "")} kn_len={len(json.dumps(n.get("knowledgeNodes",[])))}')
print(f'mappingCoverage={data.get("mappingCoverage",{})}')
