import os
import csv
import urllib.request

CSV_PATH = "exhibitors_list.csv"
MAP_PDF_URL = "https://www.snec-pv.com/upload/files/snec_expo_floor_plan.pdf"  # Placeholder / official layout PDF link
LOCAL_PDF_NAME = "snec_expo_floor_plan.pdf"

# Clover layout leaf transitions and estimated walking times (minutes)
TRANSITIONS = {
    ("Leaf A", "Leaf B"): 5,
    ("Leaf B", "Leaf C"): 8,
    ("Leaf C", "Leaf D"): 5,
    ("Leaf D", "Leaf A"): 8,
    ("Leaf A", "Leaf C"): 10,
    ("Leaf B", "Leaf D"): 10
}

HALL_TO_LEAF = {
    "1.1H": "Leaf A", "1.2H": "Leaf A", "2.1H": "Leaf A", "2.2H": "Leaf A",
    "3H": "Leaf B", "4.1H": "Leaf B",
    "5.1H": "Leaf C", "5.2H": "Leaf C", "6.1H": "Leaf C", "6.2H": "Leaf C",
    "7.1H": "Leaf D", "7.2H": "Leaf D", "8.1H": "Leaf D", "8.2H": "Leaf D"
}

def load_exhibitors():
    exhibitors = []
    if not os.path.exists(CSV_PATH):
        print(f"[-] Error: {CSV_PATH} not found!")
        return exhibitors
    
    with open(CSV_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            exhibitors.append(row)
    return exhibitors

def search_exhibitors(query, field="Company Name"):
    exhibitors = load_exhibitors()
    results = []
    for ex in exhibitors:
        if query.lower() in ex[field].lower():
            results.append(ex)
    return results

def download_floorplan_pdf():
    print("[*] Initiating Floor Plan download from SNEC server...")
    try:
        # Since this is a demonstration environment, we download the official representative PDF
        # or fall back to an informational guide if there's no internet connectivity or the URL fails.
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(MAP_PDF_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response, open(LOCAL_PDF_NAME, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        print(f"[+] Success! SNEC Floor Plan PDF saved to: {os.path.abspath(LOCAL_PDF_NAME)}")
        return True
    except Exception as e:
        print(f"[-] Direct PDF download failed/timed out: {e}")
        print("[*] Creating a local informational placeholder PDF representation for the tour guide model...")
        create_fallback_pdf()
        return False

def create_fallback_pdf():
    # Write a simple helper file summarizing the visual layout coordinates
    with open("snec_expo_floor_plan_readme.txt", "w", encoding="utf-8") as f:
        f.write("SNEC EXPO FLOOR PLAN & VENUE DATA SHEET\n")
        f.write("=========================================\n\n")
        f.write("This file serves as the fallback reference database for the SNEC Expo Tour Guide AI.\n\n")
        f.write("NECC SHANGHAI CLOVER LEAF DATA:\n")
        f.write("- LEAF A: Halls 1.1H, 1.2H, 2.1H, 2.2H (Primary focus: Production Equipment, Materials)\n")
        f.write("- LEAF B: Halls 3H, 4.1H (Primary focus: Racking & Mounting Systems, String Inverters)\n")
        f.write("- LEAF C: Halls 5.1H, 5.2H, 6.1H, 6.2H (Primary focus: C&I Inverters, Energy Storage Systems)\n")
        f.write("- LEAF D: Halls 7.1H, 7.2H, 8.1H, 8.2H (Primary focus: Tier 1 Modules, Utility Battery Cells & PCS)\n\n")
        f.write("METRO TRANSIT INTEGRATION:\n")
        f.write("- Line 2 East Xujing Station: Access Leaf B and C directly via East Plaza.\n")
        f.write("- Line 17 Zhugeguang Road Station: Access Leaf A and D directly via pedestrian flyover to West Plaza.\n")
    print(f"[+] Fallback floor plan data sheet created at: {os.path.abspath('snec_expo_floor_plan_readme.txt')}")

def calculate_itinerary(sector_pref):
    exhibitors = load_exhibitors()
    filtered = [ex for ex in exhibitors if sector_pref.lower() in ex["Sector"].lower()]
    
    if not filtered:
        print(f"[-] No exhibitors found for sector: {sector_pref}")
        return
    
    # Sort exhibitors by Leaf and Hall to optimize walking path
    def sort_key(ex):
        hall = ex["Hall"]
        leaf = HALL_TO_LEAF.get(hall, "Leaf A")
        return (leaf, hall, ex["Booth"])
    
    filtered.sort(key=sort_key)
    
    print(f"\n========================================================")
    print(f"🎯 OPTIMIZED EXPO TOUR ITINERARY: {sector_pref.upper()} TOUR")
    print(f"========================================================")
    print("Suggested Entry Point:")
    if HALL_TO_LEAF.get(filtered[0]["Hall"]) in ["Leaf A", "Leaf D"]:
        print(" -> West Plaza Entrance (Metro Line 17 - Zhugeguang Road Station)")
    else:
        print(" -> East Plaza Entrance (Metro Line 2 - East Xujing Station)")
    print("--------------------------------------------------------")
    
    current_leaf = None
    total_walk_time = 0
    
    for i, ex in enumerate(filtered):
        target_leaf = HALL_TO_LEAF.get(ex["Hall"], "Leaf A")
        
        if current_leaf and target_leaf != current_leaf:
            # Calculate transition walking time
            walk_key = (current_leaf, target_leaf)
            reverse_key = (target_leaf, current_leaf)
            walk_time = TRANSITIONS.get(walk_key, TRANSITIONS.get(reverse_key, 5))
            total_walk_time += walk_time
            print(f"\n🚶 [Transition] Walk from {current_leaf} to {target_leaf} (~{walk_time} mins via 2F corridor)")
        
        current_leaf = target_leaf
        print(f"\n📍 Stop #{i+1}: Hall {ex['Hall']} | Booth {ex['Booth']}")
        print(f"   🏢 Company: {ex['Company Name']} ({ex['Country']})")
        print(f"   ⚙️ Tech: {ex['Primary Technology']}")
        print(f"   📦 Products: {ex['Key Products']}")
        
    print(f"\n========================================================")
    print(f"🏁 Tour Complete! Total estimated inter-leaf walking time: {total_walk_time} minutes.")
    print(f"========================================================\n")

if __name__ == "__main__":
    print("===========================================")
    print("🔋 SNEC Expo Tour Guide AI - Research Agent 🤖")
    print("===========================================")
    
    # Run the PDF Floor Plan download process
    download_floorplan_pdf()
    
    # Perform a sample search demonstration
    print("\n[*] Demonstration Query: Searching for 'Huawei'...")
    search_results = search_exhibitors("Huawei")
    for r in search_results:
        print(f" -> Found: {r['Company Name']} in Hall {r['Hall']} (Booth {r['Booth']}) - {r['Primary Technology']}")
        
    # Generate custom itineraries
    calculate_itinerary("Battery")
    calculate_itinerary("Hydrogen")
