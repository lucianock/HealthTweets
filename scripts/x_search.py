import argparse
import os
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone

import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
import tweepy
import re


@dataclass
class TweetRecord:
	"""Estructura de datos para almacenar información de un tuit"""
	id: str
	date: str
	user_username: str
	user_displayname: str
	content: str
	like_count: int
	retweet_count: int
	reply_count: int
	quote_count: int
	lang: Optional[str]
	url: str
	external_urls: Optional[str]
	is_retweet: bool = False
	is_quote: bool = False
	is_reply: bool = False
	referenced_tweet_id: Optional[str] = None
	referenced_tweet_text: Optional[str] = None


# Grupos predefinidos de hashtags para búsquedas temáticas
PRESETS = {
	"fabry": [
		"#Fabry", "#FabryDisease", "#FabryAwareness", "#FabryHeroes",
		"#LivingWithFabry", "#FabryTreatment", "#FabryCommunity",
		"#EnfermedadDeFabry", "#FabryEspañol", "#FabryLatAm",
		"#DiagnósticoPrecozFabry", "#TratamientoFabry", "#VisibilidadFabry",
		"#VidaConFabry", "#HéroesFabry", "#MesDeConcienciaciónFabry", "#GenéticaFabry",
	],
	"glp1": [
		"#GLP1", "#GLP-1", "#Semaglutide", "#Ozempic", "#Wegovy", "#Mounjaro",
		"#Obesity", "#WeightLossJourney", "#ObesityTreatment", "#WeightManagement",
		"#GLP1Drugs", "#GLP1Medications", "#Obesidad", "#SaludMetabólica",
		"#EfectosSecundariosGLP1", "#MedicamentosObesidad",
	],
}


def ymd_to_rfc3339(date_ymd: str, end_of_day: bool = False) -> str:
	"""Convierte fecha YYYY-MM-DD a formato RFC3339 para la API de Twitter"""
	return f"{date_ymd}T23:59:59Z" if end_of_day else f"{date_ymd}T00:00:00Z"


def build_query(hashtags: List[str], lang: Optional[str]) -> str:
	"""Construye query de búsqueda combinando hashtags con OR y filtro de idioma"""
	terms: List[str] = []
	if hashtags:
		or_group = " OR ".join(hashtags)
		terms.append(f"({or_group})")
	if lang:
		terms.append(f"lang:{lang}")
	return " ".join(terms) if terms else "*"


def get_client(wait_on_rate_limit: bool) -> tweepy.Client:
	"""Inicializa cliente de Twitter API con token de autenticación"""
	load_dotenv()
	bearer = os.getenv("X_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN")
	if not bearer:
		raise RuntimeError("Missing X_BEARER_TOKEN in .env")
	return tweepy.Client(bearer_token=bearer, wait_on_rate_limit=wait_on_rate_limit)


def map_users(includes: Optional[Dict]) -> Dict[str, Dict[str, str]]:
	"""Mapea información de usuarios desde la respuesta de la API"""
	user_map: Dict[str, Dict[str, str]] = {}
	if includes and "users" in includes:
		for u in includes["users"]:
			user_map[u["id"]] = {
				"username": u.get("username", ""),
				"name": u.get("name", ""),
			}
	return user_map


def search_tweets(client: tweepy.Client, query: str, limit: Optional[int], start_time: Optional[str], end_time: Optional[str], debug: bool = False) -> List[TweetRecord]:
	"""Busca tuits usando la API de Twitter y extrae toda la información relevante"""
	rows: List[TweetRecord] = []
	max_per_page = 100  # Máximo permitido por la API
	fetched = 0

	# Configuración de la búsqueda
	kwargs = {
		"query": query,
		"tweet_fields": ["id", "created_at", "lang", "public_metrics", "entities", "referenced_tweets", "conversation_id", "in_reply_to_user_id"],
		"user_fields": ["id", "name", "username"],
		"expansions": ["author_id", "referenced_tweets.id"],
		"max_results": max_per_page,
	}
	if start_time:
		kwargs["start_time"] = start_time
	if end_time:
		kwargs["end_time"] = end_time

	if debug:
		print(f"🔍 Query: {query}")
		print(f"📅 Time range: {start_time or 'any'} to {end_time or 'now'}")
		print(f"📊 Max per page: {max_per_page}, limit: {limit or 'none'}")

	# Búsqueda paginada
	paginator = tweepy.Paginator(client.search_recent_tweets, **kwargs)
	try:
		for page in tqdm(paginator, desc="Fetching tweets"):
			if debug:
				print(f"📄 Page result count: {len(page.data or [])}")
				if hasattr(page, 'meta'):
					meta = page.meta
					print(f"📈 Result count: {meta.get('result_count', 'unknown')}")
					if 'next_token' in meta:
						print(f"➡️  Next token available: {meta['next_token'][:20]}...")
			
			# Procesar respuesta de la API
			includes = getattr(page, "includes", None)
			users_by_id = map_users(includes)
			
			# Mapear tuits referenciados para obtener su texto
			referenced_tweets_map: Dict[str, Dict] = {}
			if includes and "tweets" in includes:
				for it in includes["tweets"]:
					ref_id = str(it.get("id"))
					if ref_id:
						referenced_tweets_map[ref_id] = it
			
			# Procesar cada tuit
			for t in page.data or []:
				metrics = t.data.get("public_metrics", {})
				author_id = t.data.get("author_id")
				user = users_by_id.get(author_id, {"username": "", "name": ""})
				
				# Extraer URLs expandidas
				entities = t.data.get("entities", {}) or {}
				urls_entity = entities.get("urls", []) or []
				expanded_urls = [u.get("expanded_url") or u.get("url") for u in urls_entity if u.get("expanded_url") or u.get("url")]

				# Determinar tipo de tuit (RT, cita, reply)
				referenced_list = t.data.get("referenced_tweets", []) or []
				is_retweet = any(r.get("type") == "retweeted" for r in referenced_list)
				is_quote = any(r.get("type") == "quoted" for r in referenced_list)
				is_reply = any(r.get("type") == "replied_to" for r in referenced_list)
				
				# Obtener texto del tuit referenciado
				first_ref_id = None
				first_ref_text = None
				if referenced_list:
					first_ref_id = str(referenced_list[0].get("id")) if referenced_list[0].get("id") else None
					if first_ref_id and first_ref_id in referenced_tweets_map:
						first_ref_text = referenced_tweets_map[first_ref_id].get("text")

				# Crear registro del tuit
				rows.append(TweetRecord(
					id=str(t.id),
					date=str(t.created_at),
					user_username=user.get("username", ""),
					user_displayname=user.get("name", ""),
					content=t.text,
					is_retweet=is_retweet,
					is_quote=is_quote,
					is_reply=is_reply,
					referenced_tweet_id=first_ref_id,
					referenced_tweet_text=first_ref_text,
					like_count=int(metrics.get("like_count", 0)),
					retweet_count=int(metrics.get("retweet_count", 0)),
					reply_count=int(metrics.get("reply_count", 0)),
					quote_count=int(metrics.get("quote_count", 0)),
					lang=t.lang,
					url=f"https://x.com/i/web/status/{t.id}",
					external_urls=" ".join(expanded_urls) if expanded_urls else None,
				))
				fetched += 1
				if limit and fetched >= limit:
					if debug:
						print(f"✅ Reached limit: {fetched}/{limit}")
					return rows
			if limit and fetched >= limit:
				break
	except tweepy.TooManyRequests as e:
		if debug:
			print(f"⏰ Rate limit exceeded: {e}")
			print("💡 Tip: Wait ~15 minutes or use --no-wait to get partial results")
		return rows
	except tweepy.BadRequest as e:
		if debug:
			print(f"❌ Bad request: {e}")
			print("💡 Tip: Check your query syntax or date range")
		return rows
	except Exception as e:
		if debug:
			print(f"❌ Error: {e}")
		return rows
	return rows


def clean_text_for_csv(text: str) -> str:
	"""Limpia texto para evitar problemas de formato en CSV (alturas excesivas)"""
	if not text:
		return text
	# Reemplazar saltos de línea múltiples con espacio simple
	text = re.sub(r'\n+', ' ', text)
	# Reemplazar espacios múltiples con espacio simple
	text = re.sub(r' +', ' ', text)
	# Eliminar espacios al inicio y final
	return text.strip()

def write_output(rows: List[TweetRecord], out_dir: str, out_format: str, meta: Optional[Dict] = None) -> str:
	"""Guarda los resultados en CSV, XLSX o JSON con metadatos de búsqueda"""
	os.makedirs(out_dir, exist_ok=True)
	timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
	filename = f"tweets_{timestamp}.{out_format}"
	out_path = os.path.join(out_dir, filename)
	
	data = [asdict(r) for r in rows]
	
	# Agregar metadatos de búsqueda a cada fila para trazabilidad
	if meta:
		for rec in data:
			rec["search_query"] = meta.get("query")
			rec["search_preset"] = meta.get("preset")
			rec["search_hashtags"] = " ".join(meta.get("hashtags", [])) if meta.get("hashtags") else None
			rec["search_lang"] = meta.get("lang")
			rec["search_since"] = meta.get("since")
			rec["search_until"] = meta.get("until")
			rec["search_executed_at"] = meta.get("executed_at")
	
	# Limpiar campos de texto para evitar problemas de formato
	for rec in data:
		rec["content"] = clean_text_for_csv(rec.get("content", ""))
		rec["referenced_tweet_text"] = clean_text_for_csv(rec.get("referenced_tweet_text", ""))
	
	df = pd.DataFrame(data)
	
	# Guardar según formato solicitado
	if out_format == "csv":
		df.to_csv(out_path, index=False, encoding="utf-8-sig")
	elif out_format == "xlsx":
		df.to_excel(out_path, index=False, engine='openpyxl')
	elif out_format == "json":
		payload = {
			"meta": meta or {},
			"data": [asdict(r) for r in rows],
		}
		with open(out_path, "w", encoding="utf-8") as f:
			json.dump(payload, f, ensure_ascii=False, indent=2)
	else:
		raise ValueError("Unsupported format: " + out_format)
	return out_path


def parse_args() -> argparse.Namespace:
	"""Configura y parsea argumentos de línea de comandos"""
	parser = argparse.ArgumentParser(description="Search tweets via X API v2.")
	group = parser.add_mutually_exclusive_group(required=True)
	group.add_argument("--hashtags", nargs="*", help="Lista de hashtags/términos a combinar con OR")
	group.add_argument("--preset", choices=sorted(PRESETS.keys()), help="Usar grupo predefinido de hashtags")
	parser.add_argument("--since", help="Fecha inicio YYYY-MM-DD (inclusiva)")
	parser.add_argument("--until", help="Fecha fin YYYY-MM-DD (exclusiva)")
	parser.add_argument("--lang", help="Filtro de idioma ISO 639-1, ej: es o en")
	parser.add_argument("--limit", type=int, help="Número máximo de posts a obtener")
	parser.add_argument("--out", help="[Deprecated] Ignorado; archivos se guardan con timestamp en data/")
	parser.add_argument("--format", choices=["csv", "xlsx", "json"], default="csv", help="Formato de salida")
	parser.add_argument("--no-wait", action="store_true", help="No esperar en rate limit; devolver resultados parciales")
	parser.add_argument("--debug", action="store_true", help="Mostrar información detallada de respuesta API y tips")
	return parser.parse_args()


def main() -> None:
	"""Función principal: ejecuta búsqueda de tuits y guarda resultados"""
	args = parse_args()
	hashtags = args.hashtags if args.hashtags else PRESETS.get(args.preset, [])
	query = build_query(hashtags, args.lang)
	
	# Calcular rangos de tiempo
	start_time = ymd_to_rfc3339(args.since) if args.since else None
	end_time = None
	if args.until:
		# Si until es hoy, ajustar a 20s antes para cumplir requisitos de API
		today_ymd = datetime.now(timezone.utc).strftime("%Y-%m-%d")
		if args.until == today_ymd:
			end_time = (datetime.now(timezone.utc) - timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
		else:
			end_time = ymd_to_rfc3339(args.until, end_of_day=True)
	
	if args.debug:
		print("🚀 Starting X API search...")
		print(f"📋 Preset: {args.preset if args.preset else 'custom hashtags'}")
		print(f"🔤 Language filter: {args.lang or 'any'}")
		print(f"📅 Date range: {args.since or 'any'} to {args.until or 'now'}")
		print(f"⏱️  Wait on rate limit: {not args.no_wait}")
	
	# Ejecutar búsqueda
	client = get_client(wait_on_rate_limit=(not args.no_wait))
	rows = search_tweets(client, query, args.limit, start_time, end_time, debug=args.debug)
	
	# Preparar metadatos para trazabilidad
	meta = {
		"query": query,
		"preset": args.preset,
		"hashtags": hashtags,
		"lang": args.lang,
		"since": args.since,
		"until": args.until,
		"executed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
	}

	# Mostrar resultados o guardar archivo
	if len(rows) == 0:
		print("⚠️  No posts found. Possible reasons:")
		print("   • Rate limit exceeded (wait ~15 minutes)")
		print("   • Monthly quota exhausted (check X Developer Portal)")
		print("   • No recent posts match your query")
		print("   • Try removing --lang filter or using --debug for details")
	else:
		out_path = write_output(rows, out_dir=os.path.join(".", "data"), out_format=args.format, meta=meta)
		print(f"✅ Saved {len(rows)} posts to {out_path}")


if __name__ == "__main__":
	main()
