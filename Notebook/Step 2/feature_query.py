# feature_query.py
from __future__ import annotations
import ast
import pandas as pd
import numpy as np
from typing import Optional


def _is_nan_like(x) -> bool:
    # pd.isna(None) -> True ; pd.isna(np.nan) -> True ; pd.isna("") -> False
    try:
        return pd.isna(x)
    except Exception:
        return False


def make_feature_query(
    filter_column: str | None,
    filter_values: str | int | float | bool | list | tuple | set | np.ndarray | None
) -> Optional[str]:
    """
    Construit une expression pour pandas.DataFrame.query() à partir de
    filter_column et filter_values. Retourne None si pas de filtre.

    Principes:
    - Garde les noms de colonnes échappés par des backticks: `col`
    - Booléens ("true"/"false" ou bool) → comparaison directe
    - Listes: inline (ex: `col` in ['a','b']) → pas de local_dict requis
    - Numériques: 123, 4.56 → comparaison directe
    - Chaînes: égalité avec quotes

    Exemples:
    >>> make_feature_query("type", "['primary','secondary']")
    "`type` in ['primary', 'secondary']"
    >>> make_feature_query("year", 2020)
    "`year` == 2020"
    >>> make_feature_query("is_urban", "true")
    "`is_urban` == True"
    """
    # Pas de colonne ou valeurs invalides → pas de filtre
    if not filter_column or _is_nan_like(filter_column) or filter_values is None or _is_nan_like(filter_values):
        return None

    col = str(filter_column).strip()
    if col == "":
        return None

    # 1) Cas: itérable déjà fourni (list/tuple/set/ndarray)
    if isinstance(filter_values, (list, tuple, set, np.ndarray)):
        lst = list(filter_values)
        return f"`{col}` in {repr(lst)}"

    # 2) Cas: string (peut être bool, liste encodée, nombre encodé, ou simple chaîne)
    if isinstance(filter_values, str):
        s = filter_values.strip()
        if s == "":
            return None

        # Bool en string
        low = s.lower()
        if low in ("true", "false"):
            val = True if low == "true" else False
            return f"`{col}` == {val}"

        # Liste encodée: "['a','b']" ou "[1,2]"
        if s.startswith("[") and s.endswith("]"):
            try:
                lst = ast.literal_eval(s)
                if isinstance(lst, (list, tuple)):
                    return f"`{col}` in {repr(list(lst))}"
            except Exception:
                # si échec, on tombera sur la branche "chaîne simple" plus bas
                pass

        # Numérique encodé en chaîne → tente conversion
        # (priorité à int si possible, sinon float)
        try:
            if "." in s or "e" in s.lower():
                val = float(s)
            else:
                val = int(s)
            return f"`{col}` == {val}"
        except Exception:
            # Pas un nombre → chaîne simple
            return f"`{col}` == {repr(s)}"

    # 3) Cas: bool/int/float natifs
    if isinstance(filter_values, (bool, int, float, np.integer, np.floating)):
        return f"`{col}` == {filter_values}"

    # Fallback: stringifier
    return f"`{col}` == {repr(str(filter_values))}"


# import ast
# import pandas as pd

# def make_feature_query(filter_column: str | None, filter_values: str | int | float | bool | None):
#     """
#     Construit une expression pour pandas.DataFrame.query() à partir de
#     filter_column et filter_values (qui peut être scalaire ou une liste encodée).
#     Retourne None si pas de filtre.
#     """
#     if not filter_column or pd.isna(filter_column) or pd.isna(filter_values):
#         return None

#     col = str(filter_column).strip()

#     # Tenter d'interpréter une liste encodée
#     if isinstance(filter_values, str):
#         s = filter_values.strip()

#         # True/False en string
#         if s.lower() in ("true", "false"):
#             val = True if s.lower() == "true" else False
#             return f"`{col}` == {val}"

#         # Liste encodée: "['a','b']"
#         if s.startswith("[") and s.endswith("]"):
#             try:
#                 lst = ast.literal_eval(s)
#                 if isinstance(lst, (list, tuple)):
#                     # pandas.query supporte "col in @lst"
#                     return f"`{col}` in @lst"
#             except Exception:
#                 pass

#         # Sinon chaîne simple
#         return f"`{col}` == {repr(s)}"

#     # Numérique/bool direct
#     return f"`{col}` == {filter_values}"
