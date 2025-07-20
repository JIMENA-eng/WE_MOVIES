from flask import Blueprint

admin_bp = Blueprint('admin', __name__, template_folder='templates')

# 👇 Asegúrate que esta línea se pone al FINAL de este archivo:
from . import routes  # ← IMPORTANTE: al final, para que cargue rutas correctamente
