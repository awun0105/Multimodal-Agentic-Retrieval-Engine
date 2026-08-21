import argparse
import concurrent.futures
import time
from gradio_client import Client

def send_query(client: Client, query: str, worker_id: int):
    print(f"[Worker {worker_id}] Gửi query: '{query}'")
    start = time.time()
    try:
        # Gọi API search_keyframes với đầy đủ 11 inputs
        result = client.predict(
            query=query,                      # query
            top_k=5,                          # top_k
            query_language="vi",              # query_language 
            collections=[],                   # collections
            video_id="",                      # video_id
            object_entities="",               # object_entities
            object_match_mode="Any",          # object_match_mode
            minimum_object_confidence=0.5,    # minimum_object_confidence
            author="",                        # author
            publish_date_from="",             # publish_date_from
            publish_date_to="",               # publish_date_to
            api_name="/search_keyframes"
        )
        end = time.time()
        
        # result thường là 1 list các return outputs. Lấy output đầu tiên để in log.
        sample_output = str(result)[:100].replace('\n', ' ')
        print(f"[Worker {worker_id}] Hoàn thành trong {end - start:.2f} giây. KQ: {sample_output}...")
        return end - start
    except Exception as e:
        end = time.time()
        print(f"[Worker {worker_id}] Lỗi sau {end - start:.2f} giây: {e}")
        return -1

def main():
    parser = argparse.ArgumentParser(description="Test Gradio app concurrency.")
    parser.add_argument("url", type=str, help="Gradio public URL (e.g., https://xxxx.gradio.live)")
    args = parser.parse_args()

    print(f"Kết nối tới Gradio app tại: {args.url}")
    client = Client(args.url)

    queries = ["A cat playing with a ball", "A red car on the street"]
    
    print(f"\nBắt đầu gửi {len(queries)} requests song song...")
    start_total = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        for i, q in enumerate(queries):
            futures.append(executor.submit(send_query, client, q, i+1))
        
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    end_total = time.time()
    print(f"\nTổng thời gian hoàn thành cả 2 request: {end_total - start_total:.2f} giây.")
    
    if all(r > 0 for r in results):
        max_single = max(results)
        print(f"Thời gian request lâu nhất: {max_single:.2f} giây.")
        if end_total < max_single * 1.5:
            print("=> KẾT LUẬN: Các request ĐÃ được xử lý song song (Multi-GPU hoạt động tốt)!")
        else:
            print("=> KẾT LUẬN: Các request CÓ THỂ đã bị xếp hàng tuần tự.")

if __name__ == "__main__":
    main()
