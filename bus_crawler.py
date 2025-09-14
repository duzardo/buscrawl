import requests
from bs4 import BeautifulSoup
import os
import time
from urllib.parse import urljoin, urlparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue

class BusCrawler:
    def __init__(self, base_url, download_dir="images", max_workers=8):
        self.base_url = base_url
        self.download_dir = download_dir
        self.max_workers = max_workers
        self.lock = threading.Lock()

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=2
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
    
    def get_page(self, url, timeout=5):
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            with self.lock:
                print(f"Erro ao acessar {url}: {e}")
            return None
    
    def extract_image_links(self, soup, page_url):
        image_links = []
        link_tags = soup.find_all('a')
        
        for link in link_tags:
            href = link.get('href')
            if not href:
                continue
            img_tag = link.find('img')
            if img_tag:
                full_url = urljoin(page_url, href)
                if self.is_valid_image_link(full_url, img_tag):
                    image_links.append(full_url)
        
        return image_links
    
    def is_valid_image_link(self, url, img_tag):
        url_lower = url.lower()
        width = img_tag.get('width')
        height = img_tag.get('height')
        
        if width and height:
            try:
                w, h = int(width), int(height)
                if w < 100 or h < 100:
                    return False
            except ValueError:
                pass
        
        exclude_keywords = ['icon', 'logo', 'favicon', 'sprite', 'menu', 'header', 'footer']
        if any(keyword in url_lower for keyword in exclude_keywords):
            return False
        
        if any(nav in url_lower for nav in ['page=', 'offset=', 'start=', 'pagina=']):
            return False
            
        return True

    def is_urban_bus_service(self, soup):
        """Verifica se o ônibus tem 'Serviço Urbano' na página e extrai o nome"""
        bus_info = self.extract_bus_service_info(soup)
        return bus_info is not None

    def extract_bus_service_info(self, soup):
        """Extrai informações do serviço urbano (número da linha e nome do ônibus)"""
        page_text = soup.get_text().replace('\n', ' ').replace('\r', ' ')


        service_patterns = [
            r'Serviço\s+Urbano:?\s*(INTER\s+\d+)',
            r'SERVIÇO\s+URBANO:?\s*(INTER\s+\d+)',
            r'Urbano:?\s*(INTER\s+\d+)',
            r'URBANO:?\s*(INTER\s+\d+)',
            r'(INTER\s+\d+).*Urbano',
            r'Urbano.*(INTER\s+\d+)',

            r'Serviço\s+Urbano:\s*([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',
            r'SERVIÇO\s+URBANO:\s*([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',
            r'Urbano:\s*([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',
            r'URBANO:\s*([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',

            r'Serviço\s+Urbano\s+([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',
            r'SERVIÇO\s+URBANO\s+([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',

            r'Tipo.*Urbano.*?([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+)',
            r'Linha\s*([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]+).*Urbano',
        ]

        for i, pattern in enumerate(service_patterns):

            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:

                if 'INTER' in pattern and len(match.groups()) == 1:
                    full_name = match.group(1)
                    return {
                        'line_number': 'INTER',
                        'bus_name': full_name.lower()
                    }

                elif len(match.groups()) >= 2:
                    line_number = match.group(1)
                    bus_name = match.group(2).strip()
                    return {
                        'line_number': line_number,
                        'bus_name': bus_name
                    }

        service_elements = soup.find_all(['td', 'div', 'span', 'p'],
                                        string=re.compile(r'Serviço.*Urbano|SERVIÇO.*URBANO', re.IGNORECASE))

        for element in service_elements:
            text = element.get_text()
            for pattern in service_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    line_number = match.group(1)
                    bus_name = match.group(2).strip()
                    return {
                        'line_number': line_number,
                        'bus_name': bus_name
                    }

        if re.search(r'urbano', page_text, re.IGNORECASE):
                fallback_patterns = [
                    r'(INTER\s+\d+)',
                    r'([A-Z]?\d+[A-Z]?)\s*-\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]{3,})',
                    r'Linha\s*([A-Z]?\d+[A-Z]?)\s*([A-ZÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ/\s\-\.]{3,})'
                ]

                for fallback in fallback_patterns:
                    match = re.search(fallback, page_text, re.IGNORECASE)
                    if match:
                        if 'INTER' in fallback and len(match.groups()) == 1:
                            inter_name = match.group(1)
                            print(f"🔄 Fallback encontrou INTER: {inter_name}")
                            return {
                                'line_number': 'INTER',
                                'bus_name': inter_name.lower()
                            }
                        elif len(match.groups()) >= 2:
                            line_num = match.group(1)
                            bus_name = match.group(2).strip()
                            if len(bus_name) > 3:
                                print(f"🔄 Fallback encontrou: {line_num} - {bus_name}")
                                return {
                                    'line_number': line_num,
                                    'bus_name': bus_name
                                }

                return {
                'line_number': 'unknown',
                'bus_name': 'urbano'
            }

        with self.lock:
            print(f"❌ Serviço urbano não encontrado")
        return None

    def get_high_res_image_url(self, image_page_url):
        print(f"🔍 Acessando página da imagem: {image_page_url}")

        response = self.get_page(image_page_url)
        if not response:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        bus_info = self.extract_bus_service_info(soup)
        if not bus_info:
            print(f"❌ Não é serviço urbano - pulando: {image_page_url}")
            return None
        
        strategies = [
            lambda s: self.enhance_onibus_brasil_detection(s, image_page_url),
            lambda s: self.find_main_image(s, image_page_url),
            lambda s: self.find_download_link(s, image_page_url),
            lambda s: self.find_meta_image(s, image_page_url)
        ]
        
        for strategy in strategies:
            image_url = strategy(soup)
            if image_url:
                return {
                    'url': image_url,
                    'bus_info': bus_info
                }

        return None
    
    def find_main_image(self, soup, page_url):
        main_image_selectors = [
            'img.main-image',
            'img.large-image', 
            'img.full-size',
            '.image-container img',
            '.main-content img',
            '.photo-view img',
            'img[src*="large"]',
            'img[src*="full"]',
            'img[src*="original"]'
        ]
        
        for selector in main_image_selectors:
            img = soup.select_one(selector)
            if img:
                src = img.get('src') or img.get('data-src')
                if src:
                    return urljoin(page_url, src)
        
        all_imgs = soup.find_all('img')
        largest_img = None
        max_size = 0
        
        for img in all_imgs:
            src = img.get('src') or img.get('data-src')
            if not src:
                continue
                
            width = img.get('width')
            height = img.get('height')
            
            if width and height:
                try:
                    size = int(width) * int(height)
                    if size > max_size:
                        max_size = size
                        largest_img = src
                except ValueError:
                    pass
        
        if largest_img:
            return urljoin(page_url, largest_img)
        
        return None
    
    def find_download_link(self, soup, page_url):
        download_selectors = [
            'a[href*="download"]',
            'a[href*="original"]',
            'a[href*="full"]',
            'a[href*="large"]',
            '.download-link',
            '.full-size-link'
        ]
        
        for selector in download_selectors:
            link = soup.select_one(selector)
            if link:
                href = link.get('href')
                if href and any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    return urljoin(page_url, href)
        
        return None
    
    def find_meta_image(self, soup, page_url):
        meta_selectors = [
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'meta[property="og:image:url"]'
        ]
        
        for selector in meta_selectors:
            meta = soup.select_one(selector)
            if meta:
                content = meta.get('content')
                if content:
                    return urljoin(page_url, content)
        
        return None
    
    def enhance_onibus_brasil_detection(self, soup, page_url):
        lightbox_selectors = [
            'img[data-lightbox]',
            'img[data-fancybox]',
            'a[data-lightbox] img',
            'a[data-fancybox] img'
        ]
        
        for selector in lightbox_selectors:
            img = soup.select_one(selector)
            if img:
                parent = img.find_parent('a')
                if parent and parent.get('href'):
                    href = parent.get('href')
                    if any(ext in href.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        return urljoin(page_url, href)
        
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                import re
                img_patterns = [
                    r'["\']([^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*)["\']',
                    r'image["\']?\s*:\s*["\']([^"\']*)["\']',
                    r'src["\']?\s*:\s*["\']([^"\']*)["\']'
                ]
                
                for pattern in img_patterns:
                    matches = re.findall(pattern, script.string, re.IGNORECASE)
                    for match in matches:
                        if 'large' in match.lower() or 'full' in match.lower() or 'original' in match.lower():
                            return urljoin(page_url, match)
        
        return None
    
    def download_image(self, image_url, filename):
        try:
            response = self.session.get(image_url, timeout=15, stream=True)
            response.raise_for_status()

            filepath = os.path.join(self.download_dir, filename)

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=16384):  # Chunks maiores
                    f.write(chunk)

            with self.lock:
                print(f"✓ Baixada: {filename}")
            return True

        except requests.RequestException as e:
            with self.lock:
                print(f"✗ Erro ao baixar {image_url}: {e}")
            return False
    
    def generate_filename(self, image_url, index, bus_info=None):
        parsed_url = urlparse(image_url)
        path = parsed_url.path

        _, ext = os.path.splitext(path)
        if not ext:
            ext = '.jpg'

        if bus_info and bus_info.get('bus_name'):
            bus_name = bus_info['bus_name']

            bus_name = re.sub(r'[^\wÀ-ÿÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ\s\-/]', '', bus_name)
            bus_name = re.sub(r'[-\s/]+', '_', bus_name)
            bus_name = bus_name.strip('_').lower()

            if bus_name and bus_name != 'urbano':
                filename = f"{index:04d}_{bus_name}{ext}"
            else:
                filename = f"{index:04d}_urbano{ext}"
        else:
            filename = f"{index:04d}_urbano{ext}"

        return filename

    def process_single_image(self, image_link, index):
        try:
            image_data = self.get_high_res_image_url(image_link)

            if not image_data:
                return None

            high_res_url = image_data['url']
            bus_info = image_data['bus_info']
            filename = self.generate_filename(high_res_url, index, bus_info)
            filepath = os.path.join(self.download_dir, filename)

            if os.path.exists(filepath):
                with self.lock:
                    print(f"⏭ Já existe: {filename}")
                return None

            with self.lock:
                print(f"📥 Baixando: {filename}")
                print(f"🚌 Linha: {bus_info.get('line_number', 'N/A')} - {bus_info.get('bus_name', 'N/A')}")

            if self.download_image(high_res_url, filename):
                return filename
            return None

        except Exception as e:
            with self.lock:
                print(f"❌ Erro no processamento: {e}")
            return None

    def process_images_parallel(self, image_links, page_num):
        valid_images = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_data = {}
            for i, image_link in enumerate(image_links):
                future = executor.submit(self.get_high_res_image_url, image_link)
                future_to_data[future] = (i, image_link)

            temp_results = [None] * len(image_links)
            for future in as_completed(future_to_data):
                original_index, image_link = future_to_data[future]
                result = future.result()
                if result:
                    temp_results[original_index] = (image_link, result)

            # Filtra e mantém ordem
            for item in temp_results:
                if item is not None:
                    valid_images.append(item)

        # Agora baixa as imagens válidas com numeração sequencial
        downloaded = []
        base_index = (page_num - 1) * 100

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_info = {}

            for seq_num, (image_link, image_data) in enumerate(valid_images, 1):
                sequential_index = base_index + seq_num
                future = executor.submit(
                    self.download_validated_image,
                    image_data,
                    sequential_index
                )
                future_to_info[future] = (seq_num, image_link)

            # Coleta resultados
            for future in as_completed(future_to_info):
                result = future.result()
                if result:
                    downloaded.append(result)

        return downloaded

    def download_validated_image(self, image_data, index):
        """Baixa uma imagem já validada (serviço urbano confirmado)"""
        try:
            high_res_url = image_data['url']
            bus_info = image_data['bus_info']
            filename = self.generate_filename(high_res_url, index, bus_info)
            filepath = os.path.join(self.download_dir, filename)

            if os.path.exists(filepath):
                with self.lock:
                    print(f"⏭ Já existe: {filename}")
                return None

            with self.lock:
                print(f"📥 Baixando: {filename}")
                print(f"🚌 Linha: {bus_info.get('line_number', 'N/A')} - {bus_info.get('bus_name', 'N/A')}")

            if self.download_image(high_res_url, filename):
                return filename
            return None

        except Exception as e:
            with self.lock:
                print(f"❌ Erro no download: {e}")
            return None

    def get_pagination_urls(self, soup, current_url):
        pagination_urls = []
        
        pagination_selectors = [
            'a[href*="page"]',
            'a[href*="pagina"]',
            '.pagination a',
            '.pager a',
            'a[href*="offset"]',
            'a[href*="start"]'
        ]
        
        for selector in pagination_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(current_url, href)
                    pagination_urls.append(full_url)
        
        pagination_urls = list(set(pagination_urls))
        if current_url in pagination_urls:
            pagination_urls.remove(current_url)
        
        return pagination_urls
    
    def crawl_page(self, page_url, page_num=1):
        print(f"\n📄 Processando página {page_num}: {page_url}")
        
        response = self.get_page(page_url)
        if not response:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        image_links = self.extract_image_links(soup, page_url)
        print(f"🔍 Encontrados {len(image_links)} links de imagens na página {page_num}")
        
        # Processamento paralelo das imagens
        downloaded = self.process_images_parallel(image_links, page_num)
        
        print(f"✅ Página {page_num} concluída: {len(downloaded)} imagens baixadas em alta resolução")
        return image_links
    
    def crawl_website(self, start_url, max_pages=None):
        print(f"🚀 Iniciando crawler para: {start_url}")
        
        visited_urls = set()
        urls_to_visit = [start_url]
        page_count = 0
        total_images = 0
        
        while urls_to_visit and (max_pages is None or page_count < max_pages):
            current_url = urls_to_visit.pop(0)
            
            if current_url in visited_urls:
                continue
            
            visited_urls.add(current_url)
            page_count += 1
            
            images = self.crawl_page(current_url, page_count)
            total_images += len(images)
            
            if max_pages is None or page_count < max_pages:
                response = self.get_page(current_url)
                if response:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    new_urls = self.get_pagination_urls(soup, current_url)
                    
                    for url in new_urls:
                        if url not in visited_urls and url not in urls_to_visit:
                            urls_to_visit.append(url)
                            print(f"🔗 Nova página encontrada: {url}")
        
        print(f"\n🎉 Crawler concluído!")
        print(f"📊 Total de páginas processadas: {page_count}")
        print(f"📸 Total de imagens encontradas: {total_images}")
        print(f"📁 Imagens salvas em: {self.download_dir}")

def main():
    base_url = "https://www.onibusbrasil.com"
    
    start_url = input("Digite a URL da página inicial para fazer o crawler: ").strip()
    
    if not start_url:
        print("❌ URL não fornecida!")
        return
    
    download_dir = "onibus_images"
    max_pages = input("Quantas páginas deseja processar? (deixe vazio para todas): ").strip()
    workers = input("Quantas threads usar? (padrão 8, máximo 16): ").strip()

    try:
        max_pages = int(max_pages) if max_pages else None
    except ValueError:
        max_pages = None

    try:
        workers = min(int(workers), 16) if workers else 8
    except ValueError:
        workers = 8

    print(f"🚀 Configuração: {workers} threads paralelas")
    crawler = BusCrawler(base_url, download_dir, max_workers=workers)
    crawler.crawl_website(start_url, max_pages)

if __name__ == "__main__":
    main()