import re
with open('app/db.py', encoding='utf-8') as f:
    c = f.read()
m = re.search(r'CREATE TABLE tickets \((.*?)\);', c, re.S)
print(m.group(1) if m else 'no tickets')
for k in ('reopened_count', 'assigned_admin_id', 'ticket_reads', 'ticket_counters', 'resolved_at'):
    print(k, k in c)
