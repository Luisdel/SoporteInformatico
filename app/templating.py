from fastapi.templating import Jinja2Templates

from app.timeutil import to_gfh

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["gfh"] = to_gfh
