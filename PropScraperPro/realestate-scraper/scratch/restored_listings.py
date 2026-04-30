@app.route("/listings")
def listings():
    """High-performance listings search with complex price parsing."""
    try:
        page = int(request.args.get("page", 1))
        per = 20
        q = request.args.get("q", "")
        city = request.args.get("city", "")
        ltype = request.args.get("type", "")
        min_p = request.args.get("min_p", "")
        max_p = request.args.get("max_p", "")
        beds = request.args.get("beds", "")
        src = request.args.get("src", "")
        has_phone = request.args.get("has_phone", "")

        conn = get_db(); c = conn.cursor()
        where = ["1=1"]
        params = []
        
        if q:
            where.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        if city:
            where.append("city = ?")
            params.append(city)
        if ltype:
            where.append("listing_type = ?")
            params.append(ltype)

        price_sql = "CAST(REPLACE(REPLACE(REPLACE(price, '$', ''), ',', ''), '/month', '') AS FLOAT)"
        if min_p and min_p.replace('.','',1).isdigit():
            where.append(f"{price_sql} >= ?")
            params.append(float(min_p))
        if max_p and max_p.replace('.','',1).isdigit():
            where.append(f"{price_sql} <= ?")
            params.append(float(max_p))

        if beds and beds.isdigit():
            where.append("CAST(beds AS INTEGER) >= ?")
            params.append(int(beds))
        if src:
            where.append("source = ?")
            params.append(src)
        if has_phone:
            where.append("(phone IS NOT NULL AND phone != '' AND phone != 'None')")

        where_str = " AND ".join(where)
        total = c.execute(f"SELECT COUNT(*) FROM listings WHERE {where_str}", params).fetchone()[0]
        
        query = f"SELECT * FROM listings WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = c.execute(query, params + [per, (page-1)*per]).fetchall()
        
        cities = [r[0] for r in c.execute("SELECT DISTINCT city FROM listings WHERE city != '' ORDER BY city").fetchall()]
        conn.close()

        return render_template("listings.html", 
                               listings=[dict(r) for r in rows],
                               total=total, page=page, per=per,
                               pages=(total+per-1)//per, 
                               q=q, city=city, ltype=ltype, 
                               min_p=min_p, max_p=max_p, beds=beds, src=src, has_phone=has_phone,
                               cities=cities,
                               now_date=datetime.now().strftime('%Y-%m-%d'))
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return f"Database Search Error: {str(e)}", 500
