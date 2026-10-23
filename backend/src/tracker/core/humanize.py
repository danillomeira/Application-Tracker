"""Texto que sai em seu nome não pode "parecer IA": sem dois-pontos, travessões, listas com hífen e clichês."""

from __future__ import annotations

import re

# Regras anexadas às instruções de toda tarefa que escreve em nome do usuário (respostas, carta, e-mails, mensagens).
HUMAN_STYLE = """
Estilo (obrigatório, o texto precisa soar escrito por uma pessoa):
- Frases simples e diretas, em primeira pessoa, como alguém escreveria num formulário ou e-mail.
- Não use dois-pontos (:), travessão (— ou –), hífen como separador ( - ), ponto e vírgula, listas com marcadores,
  negrito, emojis nem aspas decorativas.
- Não comece com saudações genéricas nem termine com frases de efeito.
- Evite clichês de IA: "apaixonado por", "sinergia", "alavancar", "no cenário atual", "além disso", "em suma",
  "vale ressaltar", "impulsionar", "robusto", "jornada", "desafiador e gratificante", "I'm excited to", "leverage",
  "passionate about", "delve", "in today's fast-paced".
- Use números concretos do perfil quando existirem, sem exagero.
"""

_CLICHES = [
    (r"\bvale ressaltar que\s*", ""),
    (r"\bAlém disso,\s*", ""),
    (r"\bEm suma,\s*", ""),
    (r"\bMoreover,\s*", ""),
    (r"\bFurthermore,\s*", ""),
    (r"\bIn summary,\s*", ""),
]


def humanize(text: str) -> str:
    """Limpa marcas típicas de texto gerado. Não muda fatos nem números; só pontuação e muletas."""
    if not text:
        return text
    t = text.replace("**", "").replace("__", "")
    t = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", t, flags=re.M)  # marcadores de lista no começo da linha
    t = re.sub(r"\s*[—–]\s*", ", ", t)  # travessões
    t = re.sub(r"(?<=\w)\s+-\s+(?=\w)", ", ", t)  # " - " como separador (não mexe em "pós-graduação", "5-7")
    t = re.sub(r"\s*;\s*", ". ", t)
    # dois-pontos no meio da frase vira ponto; preserva horas (14:30) e links (https://)
    t = re.sub(r"(?<![\d/]):(?!//)(?!\d)\s*", ". ", t)
    for pat, rep in _CLICHES:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    # maiúscula depois de ponto (o que virou frase nova)
    t = re.sub(r"([.!?]\s+)([a-zà-ú])", lambda m: m.group(1) + m.group(2).upper(), t)
    t = re.sub(r"^([a-zà-ú])", lambda m: m.group(1).upper(), t, flags=re.M)  # começo de linha
    return t.strip()
