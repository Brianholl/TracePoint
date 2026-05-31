"""
Configuración global de pytest para TracePoint.

Con `tests/__init__.py` presente, pytest usa modo de import "prepend" e inserta
la raíz del proyecto en sys.path, de modo que `import modules.*` funciona sin
instalar el paquete. No se necesita nada más acá por ahora.
"""
