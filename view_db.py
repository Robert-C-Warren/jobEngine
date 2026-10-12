from db import get_all_jobs

jobs = get_all_jobs()
print(f"Total jobs in DB: {len(jobs)}")
for idx, j in enumerate(jobs[:15], 1):
    print(f"{idx}. [{j['company']}] {j['title']} | Loc: {j['location']} | Salary: {j['salary_range']} | Source: {j['source']}")
