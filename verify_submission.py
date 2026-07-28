import json

with open("submission.jsonl", encoding="utf-8") as f:
    lines = [l.strip() for l in f if l.strip()]

print(f"Total lines: {len(lines)}")
for line in lines:
    obj = json.loads(line)
    tid = obj["test_id"]
    body = obj["body"]
    cta = obj["cta"]
    send_as = obj["send_as"]
    if len(body) < 40:
        status = "SUSPICIOUS (short)"
    else:
        status = "OK"
    print(f"  [{status}] {tid} cta={cta} send_as={send_as}: {body[:80]}")
