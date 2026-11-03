with open('app/routes/public.py', encoding='utf-8') as f: c=f.read()
old = '    except ValueError as e:\n        raise HTTPException(status_code=400, detail=str(e))\n    if token and not request.cookies.get("device"):'
new = '    except ValueError as e:\n        raise HTTPException(status_code=400, detail=str(e))\n    from app.requesters import update_requester\n    try:\n        update_requester(conn, requester["id"], name=name, department_id=dept_id, device_name=device_name or "")\n    except Exception:\n        pass\n    if token and not request.cookies.get("device"):'
c = c.replace(old, new)
with open('app/routes/public.py','w') as f: f.write(c)
print('ok')
