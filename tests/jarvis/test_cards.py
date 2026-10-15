from jarvis.cards import card_for


def test_agenda_com_periodo():
    c = card_for(
        "buscar_eventos",
        {"de": "2026-10-09", "ate": "2026-10-09"},
        {"eventos": [{"titulo": "Dentista"}], "total": 1, "omitidos": 0},
    )
    assert c == {
        "kind": "agenda",
        "title": "Agenda · 09/10",
        "items": [{"titulo": "Dentista"}],
        "omitted": 0,
    }


def test_fatura():
    data = {
        "cartao": "Nubank",
        "vencimento": "08/11/2026",
        "fechamento": "31/10/2026",
        "situacao": "aberta",
        "total": "R$ 47,00",
        "lancamentos": 1,
        "maiores_itens": [],
    }
    c = card_for("total_fatura", {}, data)
    assert c["kind"] == "fatura" and c["title"] == "Fatura Nubank" and c["total"] == "R$ 47,00"


def test_grafico_usa_centavos_do_nucleo():
    data = {
        "periodo": "01/09/2026 a 30/09/2026",
        "total": "R$ 100,00",
        "grupos": [
            {"grupo": "Mercado", "total": "R$ 60,00", "total_centavos": 6000, "lancamentos": 2}
        ],
    }
    c = card_for("resumo_gastos", {"agrupar_por": "categoria"}, data)
    assert c["series"] == [{"label": "Mercado", "value": 6000, "display": "R$ 60,00", "count": 2}]


def test_erro_com_opcoes_vira_cartao_de_atencao():
    c = card_for("lancar_gasto", {}, {"erro": "'itaú' é ambíguo", "opcoes": ["A", "B"]})
    assert c == {
        "kind": "texto",
        "title": "Atenção",
        "text": "'itaú' é ambíguo",
        "options": ["A", "B"],
    }


def test_sem_cartao_para_abrir_app():
    assert card_for("abrir_app", {"nome": "Safari"}, {"status": "aberto"}) is None


def test_arquivos():
    c = card_for("buscar_arquivo", {"texto": "contrato"}, {"arquivos": ["~/a.pdf"], "total": 1})
    assert c["kind"] == "arquivos" and c["items"] == ["~/a.pdf"]


# --- projeto e rascunho (jarvis-projetos)


def test_projeto_aberto_vira_texto():
    data = {
        "status": "aberto",
        "pasta": "NC-BARBER",
        "editor": "aberto",
        "terminal": {"numero": 3, "tipo": "shell", "existente": True},
    }
    c = card_for("abrir_projeto", {"nome": "NC Barber"}, data)
    assert c == {
        "kind": "texto",
        "title": "Projeto",
        "text": "NC-BARBER · editor aberto · Terminal 3 (já aberto)",
    }
    data["editor"], data["terminal"]["existente"] = "não encontrei o app 'X'", False
    assert card_for("abrir_projeto", {}, data)["text"] == (
        "NC-BARBER · não encontrei o app 'X' · Terminal 3"
    )


def test_rascunho_leva_o_texto_inteiro():
    data = {
        "status": "pronto",
        "tipo": "email",
        "para": "professor",
        "assunto": "Segunda chamada",
        "texto": "Prezado professor,\n\nKaio",
        "arquivo": "~/x.md",
        "_fala": "fixa",
    }
    assert card_for("rascunho", {}, data) == {
        "kind": "rascunho",
        "title": "Rascunho · e-mail para professor",
        "to": "professor",
        "subject": "Segunda chamada",
        "text": "Prezado professor,\n\nKaio",
        "file": "~/x.md",
    }
    sem = card_for("rascunho", {}, {"status": "pronto", "tipo": "mensagem", "texto": "oi"})
    assert sem["title"] == "Rascunho · mensagem" and sem["to"] is None
