# Radar de Captação

**Identifique edifícios com anúncios imobiliários e organize oportunidades de captação.**

Aplicação web **local-first**, gratuita para execução local, com painel responsivo, backend Python/FastAPI, banco SQLite, organização de anúncios por prédio, **sincronização automática de feeds autorizados** e controle do funil de prospecção.

> **Atenção:** a ferramenta não extrai anúncios automaticamente do ZAP Imóveis, Viva Real ou outros portais. Ela pode importar dados fornecidos por você e sincronizar **feeds CSV/JSON para os quais você tem autorização de acesso e uso**. Ela não revela proprietários nem endereços ocultos.

## 1. Primeiros passos (Windows)

1. Instale o **Python 3.11 ou mais recente** em [python.org](https://www.python.org/downloads/) e marque a opção **Add Python to PATH**. É necessário acesso à internet para instalar as dependências na primeira execução.
2. Extraia o projeto ZIP ou clone este repositório.
3. Execute o arquivo **`iniciar_windows.bat`** na pasta raiz.
4. Aguarde a instalação inicial das dependências e a mensagem `Uvicorn running...`.
5. O navegador abre automaticamente depois que `/api/health` responde. Caso necessário, acesse **http://127.0.0.1:8000**. Mantenha o terminal aberto.

O banco de dados é criado automaticamente em `backend/data/radar.db`. Ele não é versionado pelo Git. **Faça cópias de segurança desse arquivo.**

Alternativa pelo PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

## 2. Usar o painel

- **Visão geral:** edifícios, anúncios, concentração por bairros e situação do funil.
- **Oportunidades:** busque edifícios, filtre por bairro e status e abra detalhes.
- **Anúncios:** consulte valores, informações disponíveis, links de origem e nível de precisão.
- **Mapa:** exibe edifícios com coordenadas informadas na importação. A visualização cartográfica usa Leaflet/OpenStreetMap via CDN, exigindo internet e disponibilidade dos serviços de mapas. Sem internet, os demais recursos continuam funcionando.
- **Fontes automáticas:** cadastre CSV/JSON na pasta `imports/` ou um feed HTTPS autorizado; sincronize quando desejar ou por intervalo enquanto o servidor estiver aberto.
- **Importar dados:** envie planilhas CSV/XLSX ou arquivos JSON. Há um modelo e dados fictícios de demonstração acessíveis pela tela.
- **Cadastro manual:** insira anúncios individualmente.
- **Exportação:** baixe anúncios ou edifícios em Excel e CSV pela API.

Para iniciar com dados fictícios, abra **Importar dados** e clique em **Carregar dados fictícios de demonstração**. Esses registros **não representam imóveis reais** e contêm endereços inventados.

## 3. Sincronização automática com fontes autorizadas

Para experimentar **sem dados reais**, abra o menu **Fontes automáticas**, preencha:

- Nome: `Demonstração agendada`.
- Tipo: `Arquivo monitorado (local)`.
- Arquivo: `exemplo_autorizado.json`.
- Intervalo: 360 minutos (pode alterar para 15 minutos no teste).
- Marque a declaração de autorização (o arquivo de exemplo contém apenas endereços inventados), clique em **Adicionar fonte** e depois em **Sincronizar agora**.

O arquivo está incluído na pasta `imports/` do projeto. **Os anúncios do exemplo são inteiramente fictícios.** Os resultados aparecem em **Oportunidades** e em **Anúncios**. Se sincronizar de novo, os registros com o mesmo código são atualizados em vez de duplicados. Para usar uma planilha própria, copie CSV ou JSON **para `imports/`** e configure o nome exato do arquivo.

Também é possível configurar a URL de um **feed HTTPS autorizado** em formato JSON (lista ou `{ "items": [...] }`) ou CSV, respeitando a licença e a finalidade da fonte. O endereço deve ser HTTPS público, porta 443, sem redirecionamento. O Radar não faz login nem simula navegação em sites. Feeds que usam tokens na URL exigem cuidado para não compartilhar ou versionar esses segredos; prefira uma integração com autenticação apropriada antes do uso comercial.

**Importante para sincronização periódica:** cada registro do feed deve trazer `id_externo` (ou `id_anuncio`) **ou** uma `url` estável, para que uma atualização não gere novos anúncios duplicados. O sistema consulta as fontes habilitadas a cada ~30 segundos e executa as que atingiram o intervalo configurado, **somente enquanto o servidor local está aberto**. A primeira sincronização ocorre automaticamente após o cadastro, na próxima verificação do agendador; o botão **Sincronizar agora** executa imediatamente. O histórico informa novas entradas, atualizações e erros. O sistema **não** marca anúncios como encerrados por sua ausência em um feed: a fonte deve fornecer explicitamente o status correto.

- Limite por fonte: 5 MB / 2.500 anúncios por execução; conexão remota com tempo limite de 8 segundos.
- Se uma fonte falhar, os anúncios já salvos continuam no banco.
- Para desativar a atualização automática sem apagar cadastros, use **Pausar**.
- Para desativar globalmente o agendador em um ambiente de teste, defina `RADAR_AUTO_SYNC=0` antes de iniciar o backend.
- Para utilizar integrações oficiais ou licenciadas de portais, obtenha os detalhes contratuais e o formato do feed diretamente com o provedor.

## 4. Formato dos arquivos

Exemplo de colunas CSV aceitas (nomes em inglês também são aceitos):

```csv
origem,id_anuncio,finalidade,tipo,preco,area,quartos,vagas,cidade,bairro,rua,numero,edificio,unidade,link
Dados autorizados,EX-001,locacao,Apartamento,2500,70,2,1,Porto Alegre,Bom Fim,Rua Exemplo,100,Edifício Demonstrativo,301,
```

- `finalidade`: `locacao`/`aluguel`/`rent` ou `venda`/`sale`;
- `numero`: o número real **divulgado** pela fonte. Deixe vazio quando não souber;
- `edificio`: nome do condomínio anunciado (não obrigatório);
- `unidade`: identificador do apartamento **se explicitamente disponível**;
- `link`: URL de referência (o Radar **não acessa** o link para preencher os dados);
- `latitude` e `longitude` (opcionais): coordenadas obtidas legitimamente. O Radar não faz geocodificação por conta própria.

São aceitos até **5 MB** e **2.500 registros por importação**. Linhas inválidas são reportadas sem interromper as demais.

## 5. Como o agrupamento funciona

O sistema é intencionalmente **conservador**:

1. **Rua normalizada + número + cidade:** agrupa por endereço completo. A confiança mostrada é `100%` para correspondência entre os valores informados, **não** uma garantia independente de que o endereço está correto.
2. **Nome do prédio + bairro + cidade:** agrupa provisoriamente com confiança heurística de `82%` e status **A verificar**. Essa porcentagem **não é uma probabilidade estatística calibrada**.
3. **Somente bairro ou rua sem número e sem edifício:** não força a associação a prédio algum. O anúncio permanece sem edifício vinculado.

Quando dois anúncios citam a **mesma unidade** no mesmo prédio e finalidade, um deles é marcado como duplicidade provável. Sem número de unidade, não assumimos que sejam o mesmo apartamento apenas por terem características semelhantes.

**Importante:** `Registros não duplicados` não significa necessariamente `unidades únicas comprovadas`. Em anúncios com unidades ocultas ainda pode haver repetição.

## 6. Fluxo de captação

Cada edifício pode receber um status:

`Novo` → `A verificar` → `Em prospecção` → `Contato realizado` → `Em negociação` → `Captado` (ou `Descartado`).

Todos os estados podem ser escolhidos livremente no painel. Cada mudança gera um registro de atividade, e observações ficam associadas ao edifício.

## 7. API e testes

Documentação interativa da API: **http://127.0.0.1:8000/api/docs**.

Endpoints principais:

| Método | Rota | Finalidade |
| --- | --- | --- |
| GET | `/api/health` | Diagnóstico |
| GET | `/api/dashboard` | Indicadores |
| GET | `/api/buildings` | Listagem com filtros/paginação |
| GET | `/api/buildings/{id}` | Detalhes e atividades |
| PATCH | `/api/buildings/{id}` | Status/observações |
| POST | `/api/buildings/{id}/activities` | Registro de atividade |
| GET | `/api/listings` | Listagem de anúncios |
| POST | `/api/listings` | Cadastro manual |
| DELETE | `/api/listings/{id}` | Excluir registro |
| POST | `/api/import/file` | Importar CSV/XLSX/JSON |
| POST | `/api/import/json` | Importar lista JSON |
| GET/POST | `/api/sources` | Listar/cadastrar fontes autorizadas |
| PATCH/DELETE | `/api/sources/{id}` | Pausar/ativar/excluir fontes |
| POST | `/api/sources/{id}/run` | Sincronizar agora |
| GET | `/api/sources/{id}/runs` | Histórico de sincronizações |
| GET | `/api/export/buildings?format=xlsx` | Exportar prédios |
| GET | `/api/export/listings?format=csv` | Exportar anúncios |

Execute os testes:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

O frontend utiliza **HTML/CSS/JavaScript puro**, servido pelo FastAPI, sem npm ou build. Essa decisão mantém a primeira versão executável localmente sem depender do registro npm. O painel pode ser migrado para React + TypeScript quando a funcionalidade comercial estiver validada.

## 8. Segurança e limitações

- **Somente uso local**: por padrão o servidor escuta `127.0.0.1` (não é acessível por outras máquinas na rede). A API não possui autenticação. **Não exponha o serviço na internet sem criar controle de acesso, isolamento, auditoria e outros mecanismos de proteção.**
- Não inclui integrações pagas, agente de IA, scraping de portais, captura de contatos, adivinhação de endereços, autenticação, múltiplas empresas nem cobrança por assinatura.
- Não assume que um anúncio esteja ativo por ter sido importado; o campo `listing_status` deve refletir informação atualizada pela fonte.
- A atualização de anúncios pode acontecer por sincronização periódica de feeds autorizados enquanto o servidor estiver aberto; ainda não há serviço de monitoramento independente do computador ligado.
- O banco é criado a partir dos modelos atuais (sem migrações Alembic neste MVP). Antes de atualizar versões futuras, faça backup de `backend/data/radar.db`.
- Respeite os termos de cada fonte e a LGPD na coleta, armazenamento, exportação e uso de dados.
- A tela de mapa usa Leaflet e OpenStreetMap via CDN, quando houver coordenadas. Os demais componentes não fazem chamadas externas.

## 9. Publicação no GitHub

Se você recebeu o projeto em ZIP e deseja trabalhar localmente com o repositório existente:

```bash
git clone https://github.com/Paulobigfat/radar-captacao.git
cd radar-captacao
# Os arquivos do projeto já estão versionados. Inicie pelo iniciar_windows.bat.
git pull origin main
```

Não suba arquivos com dados reais, bancos de dados nem tokens pessoais. O `.gitignore` exclui o banco local e o conteúdo da pasta `imports/` exceto o exemplo fictício.

---

**Stack:** Python • FastAPI • SQLAlchemy • SQLite • OpenPyXL • HTML/CSS/JavaScript • Leaflet (mapa opcional).


### Se o navegador ficar carregando indefinidamente

A aplicação precisa ser acessada em `http://127.0.0.1:8000/` com o arquivo `iniciar_windows.bat` aberto. Não abra `static/index.html` diretamente, nem utilize caminhos `file:///...`. Para testar o servidor, acesse `http://127.0.0.1:8000/api/health` e confirme que aparece `"status": "ok"`. Se a página estiver antiga, force uma recarga com `Ctrl+F5` e verifique o console do navegador em `F12`.
