# Relatório técnico — Radar de Captação v0.3

## Entrega

- Todo o conjunto da versão 0.2: painel, FastAPI, SQLite, importação CSV/JSON/XLSX, feeds, deduplicação, agrupamento, funil e exportações.
- **Varredura de imobiliárias sem API/login**: recebe URL HTTPS pública, verifica `robots.txt`, percorre HTML e sitemaps, segue apenas links do domínio e limita 24 páginas por varredura.
- Extrai campos anunciados em JSON-LD Schema.org quando presentes e usa heurísticas conservadoras de HTML para encontrar rua/número públicos, preço, bairro, cidade, área e finalidade.
- Bloqueia redes privadas, URLs não HTTPS, redirecionamentos e dados de fontes cujo `robots.txt` negue o acesso. Não tenta CAPTCHA/login ou conteúdo privado.
- Fila de execução em segundo plano com histórico consultável, sem travar a interface.
- Relatório e exportação de anúncios por **zona, bairro, rua e número**, usando arquivo configurável `config/zonas.json`, com precisão explícita.

## Verificações

- Testes automatizados do backend e crawler em fixtures HTTP fictícias, incluindo casos de bloqueio e endereços não divulgados.
- Verificação de sintaxe de JavaScript e compilação Python.
- Verificação da API com cliente de testes FastAPI/SQLite.

## Limitações reconhecidas

- Sites que renderizam anúncios apenas por JavaScript, protegem páginas ou alteram HTML podem não produzir registros. Não há conectores específicos para marcas; a compatibilidade real deve ser testada por domínio.
- `robots.txt` e URLs públicas não equivalem a uma licença automática de reutilização; o uso deve respeitar termos e legislação aplicáveis. O objetivo declarado como acadêmico não substitui esses cuidados.
- Endereços não divulgados permanecem incompletos. O relatório indica imóveis **anunciados e observados**, não confirmação de unidades desocupadas.
- A classificação geográfica por zona é **indicativa e configurável**. Porto Alegre possui apenas bairros de exemplo; demais bairros/cidades ficam sem classificação até inclusão no mapa.
- A varredura só roda enquanto o servidor local estiver aberto. O aplicativo não foi preparado para exposição pública sem login/autorização.
