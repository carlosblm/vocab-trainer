"""Caso de uso: marcar que la definición de un `mcq_definition` no encaja en su
frase.

Es el sentido único del léxico, pero no el de esa frase («paved the way», D-036).
La marca es del contexto y de su sentido actual: ese contexto deja de dar
`mcq_definition` mientras su sentido sea ese, y pasa a `cloze_original`. Es
dato del usuario, como el progreso, y la importación no lo toca (D-012).
"""

from vocab.application.next_exercise import DefinitionExercise
from vocab.domain.models import DefinitionFlag
from vocab.ports.repository import DefinitionFlagRepository


def flag_definition(
    repository: DefinitionFlagRepository, item: DefinitionExercise
) -> DefinitionFlag:
    """Guarda la marca del contexto de `item` con su sentido actual y la
    devuelve. Solo un `mcq_definition` se marca: es el único que enseña una
    definición.

    Confirmar es de quien abre la transacción.
    """
    flag = DefinitionFlag.for_context(item.entry, item.context)
    repository.save_definition_flag(repository.ensure_user(), flag)
    return flag
