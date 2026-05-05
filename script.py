import feedparser
import pandas as pd
import urllib.parse
import re
from collections import Counter
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
import os

# Setup NLTK
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('punkt_tab', quiet=True)

stop_words = set(stopwords.words('portuguese'))

# FULL LIST OF MUNICIPALITIES
municipios = [
    "Água Clara", "Amambai", "Anastácio", "Angélica", "Aparecida do Taboado",
    "Aral Moreira", "Bataguassu", "Batayporã", "Bela Vista", "Brasilândia",
    "Caarapó", "Cassilândia", "Chapadão do Sul", "Coronel Sapucaia", "Deodápolis",
    "Dois Irmãos do Buriti", "Eldorado", "Fátima do Sul", "Glória de Dourados",
    "Iguatemi", "Itaporã", "Itaquiraí", "Ivinhema", "Jardim", "Ladário",
    "Miranda", "Mundo Novo", "Naviraí", "Nova Andradina", "Paranaíba",
    "Paranhos", "Porto Murtinho", "Ribas do Rio Pardo", "Sete Quedas", "Sonora", "Tacuru"
]

def limpar_html(texto):
    texto = re.sub(r'<.*?>', '', str(texto))
    texto = texto.replace('&nbsp;', ' ').replace('&amp;', '&')
    return texto.strip()

def buscar_noticias_google_news(municipio, categoria, consulta_str, limite=5):
    """
    Busca notícias baseada em uma consulta específica e rotula com uma categoria.
    """
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(consulta_str)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    feed = feedparser.parse(url)
    
    resultados = []
    for item in feed.entries[:limite]:
        resultados.append({
            "municipio": municipio,
            "categoria": categoria,  # Nova coluna para facilitar o filtro no Power BI
            "titulo": item.get("title", ""),
            "fonte": item.get("source", {}).get("title", "") if isinstance(item.get("source"), dict) else "",
            "data": item.get("published", ""),
            "resumo": limpar_html(item.get("summary", "")),
            "link": item.get("link", "")
        })
    return resultados

# --- DEFINIÇÃO DAS ESTRUTURAS DE CONSULTA ---
# Criamos um dicionário para iterar as categorias facilmente
categorias_queries = {
    "Social e Cultura": (
        "(Sesc OR Sesi OR 'turismo social' OR 'atividade física' OR 'qualidade de vida' OR "
        "lazer OR cultura OR teatro OR show OR 'evento cultural' OR 'programação cultural' OR "
        "'saúde do trabalhador' OR 'exame médico' OR 'unidade móvel') "
        "-crime -homicídio -assassinato -morte -policial -preso"
    ),
    "Educação e Negócios": (
        "(Senac OR Senai OR Sebrae OR 'curso técnico' OR 'capacitação' OR 'qualificação profissional' OR "
        "'jovem aprendiz' OR 'vaga de emprego' OR 'vagas abertas' OR 'empreendedorismo' OR "
        "'pequenas empresas' OR 'indústria' OR 'comércio' OR 'palestra' OR 'workshop') "
        "-crime -homicídio -assassinato -morte -tráfico"
    ),
    "Política e Institucional": (
        "('Prefeitura Municipal' OR 'Câmara Municipal' OR 'vereador' OR 'prefeito' OR 'licitação' OR "
        "'parceria pública' OR 'convênio' OR 'Fecomércio' OR 'Fiems' OR 'Famasul' OR "
        "'sindicato patronal' OR 'sindicato rural' OR 'acordo coletivo' OR 'reunião institucional') "
        "-crime -homicídio -assassinato -morte -corrupção -investigação"
    )
}


def resumo_automatico(texto, max_frases=3):
    if not texto or len(texto.strip()) == 0:
        return "Sem conteúdo suficiente para resumir."
    frases = sent_tokenize(texto, language='portuguese')
    if len(frases) <= max_frases:
        return " ".join(frases)
    palavras = word_tokenize(texto.lower(), language='portuguese')
    palavras_filtradas = [p for p in palavras if p.isalpha() and p not in stop_words and len(p) > 2]
    freq = Counter(palavras_filtradas)
    pontuacao_frases = {}
    for frase in frases:
        palavras_frase = word_tokenize(frase.lower(), language='portuguese')
        score = sum(freq.get(p, 0) for p in palavras_frase)
        pontuacao_frases[frase] = score
    top_frases = sorted(pontuacao_frases, key=pontuacao_frases.get, reverse=True)[:max_frases]
    top_frases_ordenadas = [f for f in frases if f in top_frases]
    return " ".join(top_frases_ordenadas)

def gerar_compilado_municipio(df_municipio):
    if df_municipio.empty:
        return "Não foram encontradas notícias recentes.", ""
    texto_base = " ".join(
        df_municipio["titulo"].fillna("").tolist() +
        df_municipio["resumo"].fillna("").tolist()
    )
    resumo = resumo_automatico(texto_base, max_frases=3)
    temas_texto = " ".join(df_municipio["titulo"].fillna("").tolist()).lower()
    palavras = re.findall(r'\b[a-záàâãéèêíïóôõöúçñ]+\b', temas_texto)
    palavras = [p for p in palavras if p not in stop_words and len(p) > 3]
    temas = [p for p, _ in Counter(palavras).most_common(5)]
    return resumo, ", ".join(temas)

# --- EXECUTION ---
todas_noticias = []

for municipio in municipios:
    print(f"--- Iniciando monitoramento: {municipio} ---")
    
    for nome_cat, termos in categorias_queries.items():
        # Monta a query completa combinando Município + Estado + Termos da Categoria
        query_completa = f'"{municipio}" "Mato Grosso do Sul" {termos}'
        
        print(f"  > Buscando {nome_cat}...")
        
        noticias = buscar_noticias_google_news(municipio, nome_cat, query_completa, limite=5)
        todas_noticias.extend(noticias)

df_noticias = pd.DataFrame(todas_noticias)

resumos = []
for municipio in municipios:
    df_mun = df_noticias[df_noticias["municipio"] == municipio].copy()
    if df_mun.empty:
        resumos.append({
            "municipio": municipio, 
            "qtd_noticias_encontradas": 0, 
            "temas_frequentes": "", 
            "resumo_para_slide": "Não foram encontradas notícias recentes."
        })
    else:
        resumo, temas = gerar_compilado_municipio(df_mun)
        resumos.append({
            "municipio": municipio, 
            "qtd_noticias_encontradas": len(df_mun), 
            "temas_frequentes": temas, 
            "resumo_para_slide": resumo
        })

df_resumos = pd.DataFrame(resumos)

# Create data directory if it doesn't exist
if not os.path.exists('data'):
    os.makedirs('data')

# Save to CSV with UTF-8-SIG for Power BI compatibility
df_noticias.to_csv("data/noticias_coletadas.csv", index=False, encoding="utf-8-sig")
df_resumos.to_csv("data/resumo_municipios.csv", index=False, encoding="utf-8-sig")

print(f"Processo concluído. Total de notícias: {len(df_noticias)}")
