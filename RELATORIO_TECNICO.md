# Relatório técnico — Radar de Captação v0.2

## Entregue

- Painel local responsivo: visão geral, oportunidades, anúncios, mapa condicional, importação e informações do produto.
- Backend FastAPI com banco SQLite, modelos de anúncios, edifícios e histórico de atividades.
- Importação em CSV, XLSX e JSON, cadastro manual, validação por registro e mensagens de erro.
- Agrupamento conservador de edifícios por cidade/rua/número e agrupamento provisório por cidade/bairro/nome.
- Atualização por origem + ID externo ou URL, com tentativa conservadora de marcar duplicidades quando a mesma unidade é explicitamente informada.
- Workflow de captação: status, observações e histórico.
- Pesquisa, filtros, paginação e exportação Excel/CSV.
- Base de dados **fictícia** e modelo de planilha para demonstração.
- Cadastro de fontes de dados autorizadas (arquivo local CSV/JSON ou feed HTTPS), sincronização periódica com servidor aberto, sincronização manual e histórico persistido.
- Proteção básica contra SSRF (recusa de endereços privados, locais e redirecionamentos), limite de tamanho, controle de execução simultânea e tratamento de falhas sem apagar o histórico de imóveis.
- Scripts de inicialização para Windows, documentação de API e testes automatizados.

## Verificação realizada

- Testes automatizados FastAPI/SQLite usando pytest: importação, normalização, agrupamento, duplicidades, filtros, status, comentários, exportação, proteção contra fórmulas em planilhas, sincronização repetida e falhas das fontes.
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
3. Contratar ou obter acesso a feeds autorizados de portais para alimentar o sistema com anúncios reais.
4. Se necessário, migrar frontend para React + TypeScript e hospedar em ambiente seguro.

## Resultado da versão 0.2

A ferramenta possui **motor de sincronização em funcionamento** para fontes autorizadas; não inclui coleta automatizada de páginas públicas do ZAP/Viva Real. A integração com essas plataformas depende de permissão ou feed oficial compatível. A execução automática depende do servidor local estar aberto.
