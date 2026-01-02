import asyncio
import os
import httpx
from fastapi import FastAPI, HTTPException, Query
import uvicorn

app = FastAPI()

# ================== CẤU HÌNH ==================
ROBLOX_COOKIE = os.environ.get("ROBLOX_COOKIE")
if not ROBLOX_COOKIE:
    # Fallback hoặc cảnh báo nếu chạy local mà quên set env
    print("WARNING: ROBLOX_COOKIE env variable is not set.")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Cookie": f".ROBLOSECURITY={ROBLOX_COOKIE}"
}

# Semaphore để giới hạn concurrency
sem = asyncio.Semaphore(10)

async def fetch_game_passes(client, uni):
    async with sem:
        try:
            u_id = uni["id"]
            p_res = await client.get(f"https://apis.roblox.com/game-passes/v1/universes/{u_id}/game-passes", headers=HEADERS)
            data = p_res.json()
            return data.get("gamePasses", [])
        except Exception:
            return []

async def fetch_price(client, gp):
    async with sem:
        try:
            if not gp.get("isForSale"):
                return None
            
            p_id = gp["productId"]
            e_res = await client.get(f"https://economy.roblox.com/v1/products/{p_id}?showPriceDetail=true", headers=HEADERS)
            eco_json = e_res.json()
            price = eco_json.get("price") or eco_json.get("PriceInRobux") or 0
            
            return [gp["id"], price]
        except Exception:
            return None

@app.get("/get-all-passes")
async def get_all_passes(userId: str = Query(..., description="The Roblox User ID")):
    if not userId:
        raise HTTPException(status_code=400, detail="Missing userId")

    final_results = []
    
    # Sử dụng httpx.AsyncClient trong context manager
    async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)) as client:
        try:
            # Bước 1: Lấy danh sách Universe
            res = await client.get(f"https://games.roblox.com/v2/users/{userId}/games?sortOrder=Asc&limit=50", headers=HEADERS)
            if res.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to fetch games: {res.text}")
                
            data_json = res.json()
            games_data = data_json.get("data", [])

            # Giai đoạn 1: Lấy tất cả gamepass từ các universe
            tasks_uni = [fetch_game_passes(client, uni) for uni in games_data]
            results_uni = await asyncio.gather(*tasks_uni)
            
            all_game_passes = []
            for passes in results_uni:
                if passes:
                    all_game_passes.extend(passes)
                
                # Kiểm tra sau khi thêm, nếu đủ 10 thì dừng (logic cũ của bạn)
                if len(all_game_passes) >= 10:
                    all_game_passes = all_game_passes[:10]
                    break

            # Giai đoạn 2: Lấy giá cho các gamepass
            tasks_price = [fetch_price(client, gp) for gp in all_game_passes]
            results_price = await asyncio.gather(*tasks_price)
            
            for result in results_price:
                if result:
                    final_results.append(result)
        
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"d": final_results}

if __name__ == "__main__":
    # Chạy server với Uvicorn khi file được chạy trực tiếp
    # uvicorn index:app --host 0.0.0.0 --port $PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)