# Relatório técnico — Radar de Captação v0.1

## Entregue

- Painel local responsivo: visão geral, oportunidades, anúncios, mapa condicional, importação e informações do produto.
- Backend FastAPI com banco SQLite, modelos de anúncios, edifícios e histórico de atividades.
- Importação em CSV, XLSX e JSON, cadastro manual, validação por registro e mensagens de erro.
- Agrupamento conservador de edifícios por cidade/rua/número e agrupamento provisório por cidade/bairro/nome.
- Atualização por origem + ID externo ou URL, com tentativa conservadora de marcar duplicidades quando a mesma unidade é explicitamente informada.
- Workflow de captação: status, observações e histórico.
- Pesquisa, filtros, paginação e exportação Excel/CSV.
- Base de dados **fictícia** e modelo de planilha para demonstração.
- Scripts de inicialização para Windows, documentação de API e testes automatizados.

## Verificação realizada

- Testes automatizados FastAPI/SQLite usando pytest: importação, normalização, agrupamento, duplicidades, filtros, status, comentários, exportação, proteção contra fórmulas em planilhas e exclusão.
- Validação de sintaxe de JavaScript com `node --check`.

- Não foi possível concluir um teste visual de ponta a ponta com navegador neste ambiente devido a uma restrição administrativa de acesso do Chromium ao servidor local. Os testes de API, estáticos e de sintaxe passaram.

## Simplificações intencionais do MVP

- Frontend usa HTML/CSS/JavaScript sem build (não React/Tailwind) para funcionar no cenário sem rede npm e com menor manutenção inicial.
- Não inclui scraping, integração oficial com portais, geocodificação ou adivinhação de endereço.
- Não inclui login, multi-tenant, migrations Alembic, assinatura SaaS ou deploy público.
- Mapa opcional via Leaflet/CDN depende de internet e de coordenadas importadas.

## Próximos passos, após validação comercial

1. Importar conjuntos de dados reais e autorizados, revisar casos incertos e medir utilidade para captação.
2. Adicionar autenticação, multiempresa, migrations e isolamento de dados antes de disponibilizar na internet.
3. Criar conectores apenas para provedores com API/feed e autorização apropriados.
4. Se necessário, migrar frontend para React + TypeScript e hospedar em ambiente seguro.
