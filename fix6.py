import io
buf = io.StringIO()
with open('app/tickets.py', 'r', encoding='utf-8') as f:
    c = f.read()
c = c.replace('client.get("ip")', 'client.ip').replace('client.get("mac")', 'client.mac').replace('client.get("hostname")', 'client.hostname').replace('client.get("user_agent")', 'client.user_agent')
buf.write(c)
with open('app/tickets.py', 'w', encoding='utf-8') as f:
    f.write(buf.getvalue())
print('tickets.py fixed')
