"""Adaptadores de las tareas con IA sobre un LLM.

Las plantillas de prompt viven en `prompts/`, dentro del paquete, indexadas por
tarea, idioma y versión (§3.3.4, regla 3).
"""

from vocab.adapters.llm.ollama import OllamaDistractorGenerator

__all__ = ["OllamaDistractorGenerator"]
