# Radar de Captação

**Identifique edifícios com anúncios imobiliários e organize oportunidades de captação.**

Aplicação web **local-first**, gratuita para execução local, com painel responsivo, backend Python/FastAPI, banco SQLite, organização de anúncios por prédio e controle do funil de prospecção.

> **Atenção:** a ferramenta não extrai anúncios automaticamente do ZAP Imóveis, Viva Real ou outros portais. Ela importa apenas dados fornecidos por você, de fontes cujo uso seja autorizado. Ela não revela proprietários nem endereços ocultos.

## 1. Primeiros passos (Windows)

1. Instale o **Python 3.11 ou mais recente** em [python.org](https://www.python.org/downloads/) e marque a opção **Add Python to PATH**. É necessário acesso à internet para instalar as dependências na primeira execução.
2. Extraia o projeto ZIP ou clone este repositório.
3. Execute o arquivo **`iniciar_windows.bat`** na pasta raiz.
4. Aguarde a instalação inicial das dependências e a mensagem `Uvicorn running...`.
5. Abra **http://127.0.0.1:8000** no navegador.

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
- **Importar dados:** envie planilhas CSV/XLSX ou arquivos JSON. Há um modelo e dados fictícios de demonstração acessíveis pela tela.
- **Cadastro manual:** insira anúncios individualmente.
- **Exportação:** baixe anúncios ou edifícios em Excel e CSV pela API.

Para iniciar com dados fictícios, abra **Importar dados** e clique em **Carregar dados fictícios de demonstração**. Esses registros **não representam imóveis reais** e contêm endereços inventados.

## 3. Formato dos arquivos

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

## 4. Como o agrupamento funciona

O sistema é intencionalmente **conservador**:

1. **Rua normalizada + número + cidade:** agrupa por endereço completo. A confiança mostrada é `100%` para correspondência entre os valores informados, **não** uma garantia independente de que o endereço está correto.
2. **Nome do prédio + bairro + cidade:** agrupa provisoriamente com confiança heurística de `82%` e status **A verificar**. Essa porcentagem **não é uma probabilidade estatística calibrada**.
3. **Somente bairro ou rua sem número e sem edifício:** não força a associação a prédio algum. O anúncio permanece sem edifício vinculado.

Quando dois anúncios citam a **mesma unidade** no mesmo prédio e finalidade, um deles é marcado como duplicidade provável. Sem número de unidade, não assumimos que sejam o mesmo apartamento apenas por terem características semelhantes.

**Importante:** `Registros não duplicados` não significa necessariamente `unidades únicas comprovadas`. Em anúncios com unidades ocultas ainda pode haver repetição.

## 5. Fluxo de captação

Cada edifício pode receber um status:

`Novo` → `A verificar` → `Em prospecção` → `Contato realizado` → `Em negociação` → `Captado` (ou `Descartado`).

Todos os estados podem ser escolhidos livremente no painel. Cada mudança gera um registro de atividade, e observações ficam associadas ao edifício.

## 6. API e testes

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
| GET | `/api/export/buildings?format=xlsx` | Exportar prédios |
| GET | `/api/export/listings?format=csv` | Exportar anúncios |

Execute os testes:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

O frontend utiliza **HTML/CSS/JavaScript puro**, servido pelo FastAPI, sem npm ou build. Essa decisão mantém a primeira versão executável localmente sem depender do registro npm. O painel pode ser migrado para React + TypeScript quando a funcionalidade comercial estiver validada.

## 7. Segurança e limitações

- **Somente uso local**: por padrão o servidor escuta `127.0.0.1` (não é acessível por outras máquinas na rede). A API não possui autenticação. **Não exponha o serviço na internet sem criar controle de acesso, isolamento, auditoria e outros mecanismos de proteção.**
- Não inclui integrações pagas, agente de IA, scraping de portais, captura de contatos, adivinhação de endereços, autenticação, múltiplas empresas nem cobrança por assinatura.
- Não assume que um anúncio esteja ativo por ter sido importado; o campo `listing_status` deve refletir informação atualizada pela fonte.
- A atualização de anúncios acontece via reimportação ou novo cadastro; ainda não há monitoramento programado.
- O banco é criado a partir dos modelos atuais (sem migrações Alembic neste MVP). Antes de atualizar versões futuras, faça backup de `backend/data/radar.db`.
- Respeite os termos de cada fonte e a LGPD na coleta, armazenamento, exportação e uso de dados.
- A tela de mapa usa Leaflet e OpenStreetMap via CDN, quando houver coordenadas. Os demais componentes não fazem chamadas externas.

## 8. Publicação no GitHub

Se você recebeu o projeto em ZIP e já criou o repositório vazio:

```bash
git clone https://github.com/Paulobigfat/radar-captacao.git
# Copie o conteúdo deste ZIP para dentro da pasta radar-captacao, sem criar uma subpasta extra.
cd radar-captacao
git add .
git commit -m "feat: implementa radar de captacao local"
git push origin main
```

Se `main` ainda não existir, crie a branch local (`git branch -M main`) antes do push. Não suba os arquivos de banco de dados nem tokens pessoais (`.gitignore` já os ignora).

---

**Stack:** Python • FastAPI • SQLAlchemy • SQLite • OpenPyXL • HTML/CSS/JavaScript • Leaflet (mapa opcional).


### Diagnóstico de carregamento

Use `http://127.0.0.1:8000/` com o inicializador aberto. Confira `http://127.0.0.1:8000/api/health` e pressione `Ctrl+F5` para recarregar a interface.
