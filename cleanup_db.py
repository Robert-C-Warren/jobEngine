import sqlite3

conn = sqlite3.connect("jobs.db")
c = conn.cursor()
c.execute("DELETE FROM jobs WHERE LOWER(location) LIKE '%versailles%'")
print("Deleted Versailles jobs:", c.rowcount)
c.execute("DELETE FROM jobs WHERE LOWER(location) LIKE '%estonia%'")
print("Deleted Estonia jobs:", c.rowcount)
c.execute("DELETE FROM jobs WHERE LOWER(location) LIKE '%mohali%' OR LOWER(location) LIKE '%ind%'")
print("Deleted non-US IND jobs:", c.rowcount)
conn.commit()
conn.close()
