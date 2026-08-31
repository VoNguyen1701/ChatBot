# src/pdf/search_links.py
import os, sys, re, time
from urllib.parse import urljoin, parse_qs, urlparse
from datetime import datetime
from typing import List, Dict, Optional
import logging

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
from tqdm import tqdm

# =========================
# SETUP PATH
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_db

# =========================
# LOGGING CONFIG
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =========================
# 1. SELENIUM DRIVER CONFIG
# =========================
def init_selenium_driver(headless=True, timeout=30):
    """
    Khởi tạo Selenium WebDriver
    
    Args:
        headless (bool): Chế độ không hiển thị UI
        timeout (int): Thời gian chờ (giây)
    
    Returns:
        WebDriver: Selenium driver instance
    """
    options = webdriver.ChromeOptions()
    
    if headless:
        options.add_argument("--headless=new")
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Thêm preferences
    prefs = {
        "profile.default_content_settings.popups": 0,
        "profile.managed_default_content_settings.images": 2  # Disable images để tăng tốc
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(timeout)
        driver.set_script_timeout(timeout)
        logger.info("✓ Selenium driver initialized")
        return driver
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Selenium: {e}")
        return None


# =========================
# DEBUG WEBSITE STRUCTURE
# =========================
def debug_website_structure(keyword="luật công ty", debug_mode=True):
    """
    Debug để xem cấu trúc website thực tế
    
    Args:
        keyword (str): Từ khóa test
        debug_mode (bool): Hiển thị chi tiết debug info
    """
    driver = init_selenium_driver(headless=False, timeout=30)  # headless=False để xem
    
    if not driver:
        logger.error("Không thể khởi tạo Selenium driver")
        return
    
    try:
        base_url = "https://thuvienphapluat.vn/page/tim-van-ban.aspx"
        search_url = f"{base_url}?keyword={keyword}&p=1"
        
        logger.info(f"🔍 Truy cập: {search_url}")
        driver.get(search_url)
        
        # Chờ page load
        time.sleep(5)
        
        # Lấy title để kiểm tra
        title = driver.title
        logger.info(f"📄 Page title: {title}")
        
        # Lấy current URL
        current_url = driver.current_url
        logger.info(f"🔗 Current URL: {current_url}")
        
        # Parse HTML
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        if debug_mode:
            # Tìm tất cả div có class chứa "van-ban"
            van_ban_divs = soup.find_all('div', class_=re.compile(r'van-ban'))
            logger.info(f"🔍 Tìm thấy {len(van_ban_divs)} div có class chứa 'van-ban':")
            for i, div in enumerate(van_ban_divs[:5]):
                logger.info(f"   {i+1}. Class: {div.get('class')}, Text: {div.get_text(strip=True)[:100]}...")
            
            # Tìm tất cả links
            all_links = soup.find_all('a', href=True)
            logger.info(f"🔗 Tìm thấy {len(all_links)} links trên trang")
            
            # Tìm links có chứa keyword trong href
            keyword_links = [a for a in all_links if keyword.lower() in a.get_text(strip=True).lower()]
            logger.info(f"🎯 Tìm thấy {len(keyword_links)} links có chứa keyword trong text:")
            for i, link in enumerate(keyword_links[:10]):
                logger.info(f"   {i+1}. Text: {link.get_text(strip=True)[:80]}")
                logger.info(f"       URL: {link.get('href')}")
            
            # Tìm các container có thể chứa kết quả
            containers = soup.find_all(['div', 'ul', 'ol'], class_=True)
            logger.info(f"📦 Tìm thấy {len(containers)} containers:")
            for i, cont in enumerate(containers[:10]):
                classes = ' '.join(cont.get('class', []))
                if len(cont.find_all('a')) > 0:  # Chỉ hiển thị container có links
                    logger.info(f"   {i+1}. Class: {classes}, Links: {len(cont.find_all('a'))}")
        
        # Lưu HTML để debug
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logger.info("💾 Đã lưu HTML vào debug_page.html")
        
    except Exception as e:
        logger.error(f"Lỗi debug: {e}")
    finally:
        driver.quit()


# =========================
# 2. SEARCH AND EXTRACT LINKS (SELENIUM) - UPDATED
# =========================
def search_links_by_keyword(keyword, max_results=50, max_pages=3, debug=False):
    """
    Tìm kiếm links từ thuvienphapluat.vn theo keyword (sử dụng Selenium)
    
    Args:
        keyword (str): Từ khóa tìm kiếm
        max_results (int): Số kết quả tối đa
        max_pages (int): Số trang tối đa để crawl
        debug (bool): Chế độ debug
    
    Returns:
        list: Danh sách dict chứa links và metadata
    """
    driver = init_selenium_driver(headless=not debug, timeout=15)
    
    if not driver:
        logger.error("Không thể khởi tạo Selenium driver")
        return []
    
    base_url = "https://thuvienphapluat.vn/page/tim-van-ban.aspx"
    results = []
    seen_urls = set()
    
    try:
        for page in range(1, max_pages + 1):
            if len(results) >= max_results:
                break
            
            logger.info(f"📄 Crawling trang {page} với keyword: '{keyword}'")
            
            # Xây dựng URL với tham số
            search_url = f"{base_url}?keyword={keyword}&p={page}"
            
            try:
                driver.get(search_url)
                
                # Chờ page load hoàn toàn
                time.sleep(3)
                
                # Kiểm tra page title
                title = driver.title
                logger.info(f"   📄 Page title: {title}")
                
                # Chờ các element kết quả load - thử nhiều selector
                wait = WebDriverWait(driver, 10)
            
                
                # Parse HTML
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Lấy tất cả link có href
                all_links = soup.find_all('a', href=True)

               # Lấy tất cả link
                all_links = soup.find_all('a', href=True)

                # Lọc link hợp lệ (quan trọng)
                result_items = []
                for a in all_links:
                    text = a.get_text(strip=True).lower()
                    href = a.get('href')

                    if not text:
                        continue
                     # ❌ Bỏ link search
                    if "tim-van-ban.aspx" in href:
                        continue

                    # ❌ Bỏ link không phải văn bản
                    if not href.startswith("http"):
                        continue


                    # Điều kiện lọc tốt hơn
                    if keyword.lower() in text and len(text) > 20:
                        result_items.append(a)

                logger.info(f"   🔗 Tìm thấy {len(result_items)} links phù hợp")
                for item in result_items:
                    if len(results) >= max_results:
                        break
                    
                    try:
                        # Xử lý khác nhau cho link element vs container
                        if item.name == 'a':
                            # Đây là link trực tiếp
                            link_elem = item
                            container = item.parent if item.parent else item
                        else:
                            # Đây là container, tìm link bên trong
                            link_elem = item.find('a')
                            container = item
                        
                        if not link_elem or not link_elem.get('href'):
                            continue
                        
                        link_url = urljoin(base_url, link_elem.get('href'))
                        
                        # Kiểm tra duplicate
                        if link_url in seen_urls:
                            continue
                        
                        seen_urls.add(link_url)
                        
                        # Lấy thông tin
                        link_text = clean_extracted_text(link_elem.get_text())
                        
                        # Lấy mô tả
                        description = ""
                        desc_elem = container.find('p', class_='description')
                        if not desc_elem:
                            desc_elem = container.find('div', class_='description')
                        if not desc_elem and container != link_elem:
                            # Thử lấy text từ container trừ link
                            desc_text = container.get_text(strip=True).replace(link_elem.get_text(), '').strip()
                            if desc_text:
                                description = clean_extracted_text(desc_text)[:200]  # Giới hạn 200 ký tự
                        elif desc_elem:
                            description = clean_extracted_text(desc_elem.get_text())
                        
                        # Lấy loại văn bản
                        doc_type = ""
                        type_elem = container.find('span', class_='doc-type')
                        if not type_elem:
                            type_elem = container.find('span', class_=re.compile(r'type'))
                        if type_elem:
                            doc_type = clean_extracted_text(type_elem.get_text())
                        
                        # Lấy ngày ban hành
                        publish_date = ""
                        date_elem = container.find('span', class_='publish-date')
                        if not date_elem:
                            date_elem = container.find('span', class_=re.compile(r'date'))
                        if date_elem:
                            publish_date = clean_extracted_text(date_elem.get_text())
                        
                        results.append({
                            'title': link_text,
                            'url': link_url,
                            'description': description,
                            'doc_type': doc_type,
                            'publish_date': publish_date,
                            'keyword': keyword,
                            'source': 'thuvienphapluat.vn',
                            'searched_at': datetime.now(),
                            'page': page
                        })
                    
                    except Exception as e:
                        logger.debug(f"Lỗi xử lý item: {e}")
                        continue
                
                # Delay giữa các trang để tránh bị block
                time.sleep(2)
            
            except Exception as e:
                logger.error(f"Lỗi crawl trang {page}: {e}")
                continue
    
    finally:
        driver.quit()
        logger.info("✓ Selenium driver closed")
    
    logger.info(f"✓ Tìm được {len(results)} links")
    return results


# =========================
# UTILITY FUNCTIONS
# =========================
def clean_extracted_text(text):
    """
    Làm sạch text được extract từ HTML
    
    Args:
        text (str): Text thô từ HTML
    
    Returns:
        str: Text đã được làm sạch
    """
    if not text:
        return ""
    
    # Loại bỏ các ký tự whitespace thừa
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Loại bỏ các ký tự đặc biệt không mong muốn
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # Loại bỏ các từ khóa không mong muốn ở cuối (như số trang, etc.)
    text = re.sub(r'\s*(trang\s*\d+|page\s*\d+)\s*$', '', text, flags=re.IGNORECASE)
    
    return text.strip()


def tokenize_keywords(keywords):
    """
    Tách keywords thành các từ riêng lẻ cho tìm kiếm
    
    Args:
        keywords (list or str): Danh sách keywords hoặc một keyword
    
    Returns:
        set: Set các từ riêng lẻ (unique, lowercase)
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    
    search_words = set()
    
    for keyword in keywords:
        if not keyword:
            continue
        
        # Tách theo khoảng trắng và loại bỏ punctuation
        words = re.findall(r'\b\w+\b', keyword.lower())
        
        # Lọc bỏ stop words quá ngắn (< 2 ký tự) hoặc quá dài (> 20 ký tự)
        filtered_words = [word for word in words if 2 <= len(word) <= 20]
        
        search_words.update(filtered_words)
    
    return search_words


# =========================
# 3. SAVE LINKS TO MONGODB
# =========================
def save_links_to_db(links, db=None):
    """
    Lưu danh sách links vào MongoDB collection 'Link'
    
    Args:
        links (list): Danh sách dict chứa thông tin links
        db: MongoDB database object (nếu None sẽ tạo connection mới)
    
    Returns:
        dict: Kết quả lưu (số document được chèn/cập nhật)
    """
    if db is None:
        db = get_db()
    
    collection = db['Link']
    result = {'inserted': 0, 'updated': 0, 'errors': 0}
    
    for link in tqdm(links, desc="💾 Lưu links vào MongoDB"):
        try:
            # Kiểm tra link đã tồn tại chưa dựa trên URL
            existing = collection.find_one({'url': link['url']})
            
            if existing:
                # Cập nhật thông tin
                current_keywords = existing.get('keywords', [])
                new_keyword = link.get('keyword')
                
                # Thêm keyword mới nếu chưa có
                if new_keyword and new_keyword not in current_keywords:
                    current_keywords.append(new_keyword)
                
                # Tạo search_keywords từ tất cả keywords
                search_keywords = tokenize_keywords(current_keywords)
                
                collection.update_one(
                    {'url': link['url']},
                    {
                        '$set': {
                            'title': link.get('title'),
                            'description': link.get('description'),
                            'doc_type': link.get('doc_type'),
                            'publish_date': link.get('publish_date'),
                            'keywords': current_keywords,
                            'search_keywords': list(search_keywords),
                            'updated_at': datetime.now()
                        },
                        '$inc': {'search_count': 1}
                    }
                )
                result['updated'] += 1
            else:
                # Chèn mới
                keywords = [link.get('keyword')] if link.get('keyword') else []
                search_keywords = tokenize_keywords(keywords)
                
                link['search_count'] = 1
                link['created_at'] = datetime.now()
                link['keywords'] = keywords
                link['search_keywords'] = list(search_keywords)
                
                collection.insert_one(link)
                result['inserted'] += 1
        
        except Exception as e:
            logger.error(f"Lỗi khi lưu link {link.get('url')}: {e}")
            result['errors'] += 1
    
    return result


# =========================
# 4. SEARCH FROM MONGODB
# =========================
def search_keywords_in_db(keywords, db=None, exact_match=False):
    """
    Tìm kiếm links trong MongoDB theo keywords (sử dụng search_keywords)
    
    Args:
        keywords (list or str): Danh sách keywords hoặc một keyword
        db: MongoDB database object
        exact_match (bool): True = tìm exact match trong keywords, False = tìm trong search_keywords
    
    Returns:
        list: Danh sách links phù hợp
    """
    if db is None:
        db = get_db()
    
    if isinstance(keywords, str):
        keywords = [keywords]
    
    collection = db['Link']
    
    if exact_match:
        # Tìm exact match trong array keywords
        results = collection.find({
            'keywords': {'$in': keywords}
        }).limit(100)
    else:
        # Tìm trong search_keywords (tokenized words)
        search_words = tokenize_keywords(keywords)
        results = collection.find({
            'search_keywords': {'$in': list(search_words)}
        }).limit(100)
    
    return list(results)


def search_links_by_title(search_text, db=None, limit=100):
    """
    Tìm kiếm links theo nội dung tiêu đề
    
    Args:
        search_text (str): Text để tìm kiếm trong tiêu đề
        db: MongoDB database object
        limit (int): Giới hạn số kết quả
    
    Returns:
        list: Danh sách links phù hợp
    """
    if db is None:
        db = get_db()
    
    collection = db['Link']
    
    results = collection.find({
        'title': {'$regex': search_text, '$options': 'i'}
    }).limit(limit)
    
    return list(results)




def get_link_statistics(db=None):
    """
    Lấy thống kê về links trong DB
    
    Returns:
        dict: Thống kê
    """
    if db is None:
        db = get_db()
    
    collection = db['Link']
    
    stats = {
        'total_links': collection.count_documents({}),
        'unique_keywords': len(collection.distinct('keywords')),
        'unique_sources': len(collection.distinct('source')),
        'avg_search_count': 0,
        'most_popular_links': [],
        'top_keywords': []
    }
    
    # Tính avg search count
    pipeline = [{'$group': {'_id': None, 'avg': {'$avg': '$search_count'}}}]
    avg_result = list(collection.aggregate(pipeline))
    if avg_result:
        stats['avg_search_count'] = avg_result[0]['avg']
    
    # Top 5 popular links
    stats['most_popular_links'] = list(
        collection.find({}).sort('search_count', -1).limit(5)
    )
    
    # Top 5 keywords
    top_keywords_pipeline = [
        {'$unwind': '$keywords'},
        {'$group': {'_id': '$keywords', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    stats['top_keywords'] = list(collection.aggregate(top_keywords_pipeline))
    
    return stats


# =========================
# 5. BATCH SEARCH & CRAWL
# =========================
def batch_search_and_save(keywords: List[str], max_results_per_keyword=50, db=None):
    """
    Tìm kiếm batch nhiều keywords và lưu vào DB
    
    Args:
        keywords (list): Danh sách keywords
        max_results_per_keyword (int): Số kết quả tối đa per keyword
        db: MongoDB database object
    
    Returns:
        dict: Kết quả tổng hợp
    """
    if db is None:
        db = get_db()
    
    all_links = []
    all_results = {'total_inserted': 0, 'total_updated': 0, 'total_errors': 0}
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🔍 BATCH SEARCH: {len(keywords)} keywords")
    logger.info(f"{'='*60}\n")
    
    for keyword in keywords:
        logger.info(f"🔎 Đang tìm kiếm: '{keyword}'")
        links = search_links_by_keyword(keyword, max_results=max_results_per_keyword, max_pages=3)
        logger.info(f"   ✓ Tìm được {len(links)} links\n")
        all_links.extend(links)
    
    if all_links:
        logger.info(f"{'='*60}")
        logger.info(f"💾 LƯU VÀO MONGODB")
        logger.info(f"{'='*60}\n")
        
        result = save_links_to_db(all_links, db)
        all_results.update(result)
        
        logger.info(f"   ✓ Chèn mới: {result['inserted']}")
        logger.info(f"   ✓ Cập nhật: {result['updated']}")
        logger.info(f"   ✗ Lỗi: {result['errors']}\n")
    
    return all_results


def display_statistics(db=None):
    """
    Hiển thị thống kê về links trong DB
    """
    if db is None:
        db = get_db()
    
    stats = get_link_statistics(db)
    
    logger.info(f"\n{'='*60}")
    logger.info("📊 THỐNG KÊ")
    logger.info(f"{'='*60}\n")
    
    logger.info(f"📁 Tổng links: {stats['total_links']}")
    logger.info(f"🏷️  Keywords: {stats['unique_keywords']}")
    logger.info(f"📚 Sources: {stats['unique_sources']}")
    logger.info(f"📈 Trung bình tìm kiếm: {stats['avg_search_count']:.2f}\n")
    
    logger.info("🔝 Top Links được tìm kiếm nhiều nhất:")
    for i, link in enumerate(stats['most_popular_links'], 1):
        logger.info(f"   {i}. {link['title'][:50]}... ({link['search_count']} lần)")
    
    logger.info("\n🏆 Top Keywords:")
    for i, kw in enumerate(stats['top_keywords'], 1):
        logger.info(f"   {i}. {kw['_id']} ({kw['count']} links)")
    
    logger.info(f"\n{'='*60}\n")


# =========================
# 6. MAIN WORKFLOW WITH USER INPUT
# =========================
def main():
    """Chạy menu chính: tìm kiếm, lưu vào DB, tìm kiếm trong DB và xem thống kê."""
    print("\n" + "="*60)
    print("🔍 THƯ VIỆN PHÁP LUẬT - TÌM KIẾM LINKS")
    print("="*60)

    while True:
        print("\n📋 MENU:")
        print("1. 🔍 Tìm kiếm links theo keyword và lưu vào MongoDB")
        print("2. 📊 Tìm links trong MongoDB theo keyword")
        print("3. 📈 Xem thống kê cơ bản")
        print("4. ❌ Thoát")

        choice = input("\n👉 Chọn chức năng (1-4): ").strip()

        if choice == '1':
            search_single_keyword()
        elif choice == '2':
            search_from_database()
        elif choice == '3':
            view_statistics()
        elif choice == '4':
            print("👋 Tạm biệt!")
            break
        else:
            print("❌ Lựa chọn không hợp lệ. Vui lòng chọn 1-4.")


def search_single_keyword():
    """Tìm kiếm một keyword từ input"""
    keyword = input("🔍 Nhập keyword cần tìm: ").strip()
    if not keyword:
        print("❌ Keyword không được để trống!")
        return

    max_results = input("📊 Số kết quả tối đa (mặc định 50): ").strip()
    max_results = int(max_results) if max_results.isdigit() else 50

    max_pages = input("📄 Số trang tối đa (mặc định 3): ").strip()
    max_pages = int(max_pages) if max_pages.isdigit() else 3

    debug = input("🐛 Bật debug mode? (y/n, mặc định n): ").strip().lower() == 'y'

    db = get_db()

    logger.info(f"\n🔍 Tìm kiếm: '{keyword}' (max_results={max_results}, max_pages={max_pages})")
    links = search_links_by_keyword(keyword, max_results=max_results, max_pages=max_pages, debug=debug)

    if links:
        logger.info(f"✓ Tìm được {len(links)} links")
        result = save_links_to_db(links, db)
        logger.info(f"💾 Lưu DB: {result['inserted']} mới, {result['updated']} cập nhật")

        # Hiển thị một số kết quả
        print(f"\n📋 {len(links)} kết quả đầu tiên:")
        for i, link in enumerate(links[:5], 1):
            print(f"{i}. {link['title'][:80]}...")
            if link.get('description'):
                print(f"   📝 {link['description'][:100]}...")
            print(f"   🔗 {link['url']}\n")
    else:
        logger.warning("❌ Không tìm thấy link nào!")


def search_batch_keywords():
    """Tìm kiếm batch từ input"""
    print("📝 Nhập các keywords (mỗi keyword một dòng, Enter trống để kết thúc):")
    keywords = []
    while True:
        keyword = input("Keyword: ").strip()
        if not keyword:
            break
        keywords.append(keyword)

    if not keywords:
        print("❌ Phải nhập ít nhất 1 keyword!")
        return

    max_results = input("📊 Số kết quả tối đa per keyword (mặc định 25): ").strip()
    max_results = int(max_results) if max_results.isdigit() else 25

    db = get_db()

    logger.info(f"\n🔄 Batch search {len(keywords)} keywords: {keywords}")
    result = batch_search_and_save(keywords, max_results_per_keyword=max_results, db=db)

    logger.info("📊 Kết quả batch:")
    logger.info(f"   ✓ Chèn mới: {result['total_inserted']}")
    logger.info(f"   ✓ Cập nhật: {result['total_updated']}")
    logger.info(f"   ❌ Lỗi: {result['total_errors']}")


def search_from_database():
    """Tìm kiếm links đã lưu trong MongoDB theo keyword"""
    db = get_db()
    keyword = input("🔍 Nhập keyword để tìm trong DB: ").strip()
    if not keyword:
        print("❌ Keyword không được để trống!")
        return

    results = search_keywords_in_db(keyword, db)
    if not results:
        print(f"❌ Không tìm thấy kết quả cho '{keyword}'")
        return

    print(f"\n📋 Tìm thấy {len(results)} kết quả cho '{keyword}':")
    for i, result in enumerate(results[:10], 1):
        print(f"\n{i}. {result.get('title', 'N/A')}")
        if result.get('description'):
            print(f"   📝 {result.get('description', '')[:120]}...")
        print(f"   🔗 {result.get('url', 'N/A')}")
        print(f"   🏷️  Keywords: {result.get('keywords', [])}")

def view_statistics():
    """Hiển thị thống kê đơn giản của collection Link"""
    db = get_db()
    stats = get_link_statistics(db)

    print("\n📊 THỐNG KÊ CƠ BẢN")
    print(f"Tổng links: {stats['total_links']}")
    print(f"Keywords khác nhau: {stats['unique_keywords']}")
    print(f"Sources khác nhau: {stats['unique_sources']}")
    print(f"Trung bình search_count: {stats['avg_search_count']:.2f}")
    print("Top 5 links:")
    for i, link in enumerate(stats['most_popular_links'], 1):
        print(f"   {i}. {link.get('title', 'N/A')[:80]}... ({link.get('search_count', 0)})")


def display_search_results(results, search_type):
    """Hiển thị kết quả tìm kiếm"""
    if not results:
        print(f"❌ Không tìm thấy kết quả cho {search_type}")
        return

    print(f"\n📋 Tìm thấy {len(results)} kết quả cho {search_type}:")

    for i, result in enumerate(results[:10], 1):  # Hiển thị tối đa 10
        print(f"\n{i}. 📄 {result.get('title', 'N/A')}")
        if result.get('doc_type'):
            print(f"   📋 Loại: {result['doc_type']}")
        if result.get('publish_date'):
            print(f"   📅 Ngày: {result['publish_date']}")
        if result.get('description'):
            print(f"   📝 Mô tả: {result['description'][:150]}...")
        print(f"   🔗 {result.get('url', 'N/A')}")
        print(f"   🏷️  Keywords: {result.get('keywords', [])}")


if __name__ == "__main__":
    main()
