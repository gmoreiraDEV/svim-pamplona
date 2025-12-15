"""
Testes básicos das ferramentas para o Agente de IA.
"""
from datetime import datetime, timedelta

from app.agent import tools as t

now = datetime.now()
future = now + timedelta(days=3)


def test_listar_profissionais_tool():
  response = t.listar_profissionais_tool.invoke({})
  # print(response)
  assert response.get("error") is None
  assert isinstance(response.get("data"), list), "data is not an array (list)"

def test_listar_servicos_profissional_tool():
  response = t.listar_servicos_profissional_tool.invoke({"profissionalId":"664608"})
  # print(response)
  assert response.get("error") is None

def test_listar_servicos_tool():
  response = t.listar_servicos_tool.invoke({
    "nome": "corte",
    # "categoria": "corte",
    "pageSize": 100,
    "page": 1
    })
  # for service in response["data"]:
  #   print(f"{service["nome"]} -> {service["id"]}")
  assert response.get("error") is None

def test_criar_agendamento_tool():
  response = t.criar_agendamento_tool.invoke({
    "servicoId": "11334669",
    "profissionalId":"664608",
    "clienteId": "77552505",
    "dataHoraInicio": "2025-12-15T11:30:00",
    "duracaoEmMinutos": "60",
    "valor": "100",
    "observacoes": "Sem observações",
    "confirmado": False,
  })
  # print(response)
  assert response.get("error") is None

def test_listar_agendamentos_tool():
  response = t.listar_agendamentos_tool.invoke({
    "dataInicio": now.isoformat(),
    "dataFim": future.isoformat()
  })
  # print(response)
  # for agendamento in response["data"]:
  #   print(f"Cliente: {agendamento["cliente"]["nome"]} -> {agendamento["cliente"]["id"]}")
  #   print(f"Servico: {agendamento["servico"]["nome"]} -> {agendamento["servico"]["id"]}")
  #   print(f"Profissional: {agendamento["profissional"]["nome"]} -> {agendamento["profissional"]["id"]}")
  #   print(f"Horário: {agendamento["dataHoraInicio"]} -> {agendamento["duracaoEmMinutos"]}")
  #   print(" --- ")
  assert response.get("error") is None
