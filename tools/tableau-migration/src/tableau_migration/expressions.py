"""Conservative identifier discovery, not a Tableau expression evaluator."""

from __future__ import annotations

import re


def expression_tokens(expression: str) -> tuple[list[tuple[str, ...]], str]:
    """Ignore quoted literals/comments while preserving bracketed field chains."""
    references: list[tuple[str, ...]] = []
    code: list[str] = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if expression.startswith("//", index):
            end = expression.find("\n", index)
            index = len(expression) if end < 0 else end
            code.append(" ")
        elif expression.startswith("/*", index):
            end = expression.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated Tableau block comment")
            index = end + 2
            code.append(" ")
        elif char in "'\"":
            quote = char
            index += 1
            while index < len(expression):
                if expression[index] == "\\":
                    index += 2
                elif expression[index] == quote:
                    if index + 1 < len(expression) and expression[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            else:
                raise ValueError("Unterminated Tableau string literal")
            code.append(" ")
        elif char == "[":
            chain: list[str] = []
            while True:
                start = index
                index += 1
                token: list[str] = []
                while index < len(expression):
                    if expression.startswith("]]", index):
                        token.append("]")
                        index += 2
                    elif expression[index] == "]":
                        index += 1
                        break
                    else:
                        token.append(expression[index])
                        index += 1
                else:
                    raise ValueError(f"Unterminated field identifier at offset {start}")
                chain.append("".join(token))
                lookahead = index
                while lookahead < len(expression) and expression[lookahead].isspace():
                    lookahead += 1
                if lookahead < len(expression) and expression[lookahead] == ".":
                    lookahead += 1
                    while lookahead < len(expression) and expression[lookahead].isspace():
                        lookahead += 1
                    if lookahead < len(expression) and expression[lookahead] == "[":
                        index = lookahead
                        continue
                break
            references.append(tuple(chain))
            code.append(" ")
        else:
            code.append(char)
            index += 1
    return references, "".join(code)


def calculation_features(expression: str) -> list[str]:
    _, code = expression_tokens(expression)
    patterns = {
        "fixed_lod": r"\bFIXED\b",
        "include_lod": r"\bINCLUDE\b",
        "exclude_lod": r"\bEXCLUDE\b",
        "lod_expression": r"\{",
        "window": r"\bWINDOW_\w+\s*\(",
        "running": r"\bRUNNING_\w+\s*\(",
        "ranking": r"\bRANK\w*\s*\(",
        "lookup": r"\bLOOKUP\s*\(",
        "spatial": r"\bMAKE(?:POINT|LINE|POLYGON)\s*\(",
        "external_script": r"\b(?:SCRIPT_|MODEL_EXTENSION_)\w*\s*\(",
        "count": r"\bCOUNT\s*\(",
        "distinct_count": r"\bCOUNTD\s*\(",
        "date_logic": r"\b(?:DATEADD|DATEDIFF|DATETRUNC|DATEPART|TODAY|NOW)\s*\(",
    }
    return sorted(name for name, pattern in patterns.items() if re.search(pattern, code, re.I))
