# AI Agent - SVIM Pamplona

Este documento consolida os conceitos de negócio do AI Agent - SVIM Pamplona.

## DefiniçÕes de negócio

### Contexto

- Agendamento, Cancelamento e Confirmação de horários na Trinks.
- Agente (Langgraph prebuilt) opera via ferramentas que executam ações do negócio, retornando saídas estruturadas.

### Objetivos do negócio

- Cliente: pessoa identificada no sistema da `Trinks` por meio de `nome | telefone`.
- Serviço: objeto o qual o cliente trata durante a conversa com o agente de IA.
- Profissional: colaborador da SVIM Pamplona que realizará o serviço.
- Horário: tempo determinado que o cliente precisa que aconteça o atendimento.

### Intents

- Cliente: virá pelo fluxo no `n8n` do diretamente para o contexto do Agente de IA
- Serviço: `criar_agendamento`, `cancelar_agendamento`, `confirmar_agendamento`
- Profissional: `buscar_profissional`, `buscar_servico_profissional`
- Horário: `listar_servicos`
