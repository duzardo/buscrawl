# BusCrawl

Web crawler para baixar imagens de ônibus urbanos do site ÔnibusBrasil. Identifica automaticamente veículos de transporte público urbano e baixa suas imagens em alta resolução.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
python bus_crawler.py
```

O programa irá solicitar:
- URL da página inicial
- Número de páginas para processar (opcional)
- Número de threads paralelas (padrão: 8)