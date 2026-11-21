Dark-evening classes by building — dataset guide
Nov 21, 2026 · @Lukas
For each university building, this dataset tells you how many students have classes there that end after dark, how often, and when. It comes from real student timetables, aggregated per building, with no personal data.
Files
You get one CSV, and possibly a JSON with the same numbers. Each has one record per building.
dark_blocks_by_building.csv: one row per building. The three breakdown columns (by end hour, weekday, month) hold small JSON objects as text.
dark_blocks_by_building.json (optional): the same rows under buildings, with the breakdowns as real JSON objects. The top level also records the settings used: dark (the dusk definition), lat and lon (the point dusk was calculated for) and min_students (the privacy threshold).
A building is identified only by its university building code (building_id, e.g. TR). There are no coordinates; see Using it for how to add them.
Columns
An occurrence is one class on one date for one student, so a weekly lecture with 40 students over 13 weeks counts 520 times.
Column
Unit
Meaning
building_id
text
University building code
students
students
Distinct students with any class in the building
students_with_dark_block
students
Of these, students with at least one class there that ends after dark
share_students_dark
0–1
students_with_dark_block / students
block_occurrences
occurrences
All class occurrences in the building
dark_block_occurrences
occurrences
Occurrences that end after dark
share_occurrences_dark
0–1
dark_block_occurrences / block_occurrences
distinct_dark_actions
classes
Distinct timetable entries with at least one dark occurrence
median_min_after_dusk
minutes
Median of how long after dusk the dark occurrences end; empty if none
max_min_after_dusk
minutes
The latest a dark occurrence ends after dusk; empty if none
dark_by_end_hour
JSON
Dark occurrences by the hour the class ends, e.g. {"17": 120, "18": 45}
dark_by_weekday
JSON
Dark occurrences by weekday, Czech abbreviations Po Út St Čt Pá So Ne (Mon–Sun)
dark_by_month
JSON
Dark occurrences by month, keys YYYY-MM

share_students_dark answers “how many people does this affect”; share_occurrences_dark and dark_block_occurrences answer “how often”.
How it was made
A class counts as dark when it ends at or after dusk on its own date, so the same 17:00 lecture is light in September and dark from late October.
Timetables of a sample of students are collected for the term. Teachers' timetables are not included.
Each timetable entry is expanded into the real dates it takes place: a one-off date, or its weekday between the start and end dates, respecting odd/even weeks.
Dusk is calculated for every date at one point for the whole university (the lat/lon in the JSON), in Czech local time, so the time change and shorter winter days are included.
An occurrence is dark when the class end time is at or after dusk.
Results are added up per building. Buildings with fewer than min_students students (default 5) are removed from the output.
What “dusk” means is set by dark in the JSON:
dark
Sun below horizon
In practice
sunset
0.83°
Sun just set, still light
civil (default)
6°
Street lights on, dark enough to feel unsafe
nautical
12°
Fully dark

In Olomouc on 21 November, sunset is about 16:03 and civil dusk about 16:39; on 21 June they are 21:01 and 21:45.
Using it
To put the data on a map you need one extra file: building coordinates, keyed by the same building code. Make a buildings.csv like this. Get the positions from the university, its campus map, or by clicking each building in Mapy.cz or Google Maps:
```csv
building_id,name,lat,lon
TR,Envelopa,49.5873,17.2606
PF,Faculty of Science,49.5925,17.2621
```

The rows above are made-up placeholders; replace them with real buildings.
Load both files and join them in Python (pandas):
import json
import pandas as pd

dark = pd.read_csv("dark_blocks_by_building.csv")
for col in ["dark_by_end_hour", "dark_by_weekday", "dark_by_month"]:
    dark[col] = dark[col].apply(json.loads)

buildings = pd.read_csv("buildings.csv")
df = dark.merge(buildings, on="building_id", how="left")
print(df[df.lat.isna()].building_id.tolist())  # codes still missing coordinates
A quick map with folium (pip install folium), circle size = students affected, colour = share affected:
import folium

m = folium.Map(location=[df.lat.mean(), df.lon.mean()], zoom_start=15)
for r in df.dropna(subset=["lat"]).itertuples():
    folium.CircleMarker(
        [r.lat, r.lon],
        radius=4 + r.students_with_dark_block ** 0.5,
        color="#c0392b" if r.share_students_dark > 0.5 else "#e67e22",
        fill=True,
        tooltip=f"{r.building_id}: {r.students_with_dark_block}/{r.students} students, "
                f"{r.dark_block_occurrences} dark classes",
    ).add_to(m)
m.save("dark_map.html")
In JavaScript, load the JSON instead: the breakdowns are already objects there, no parsing needed.
Ideas
The data shows where and when students leave buildings in the dark; your emotional map can show how that feels. Some starting points:
Exposure layer: weight each building by students_with_dark_block and put it next to the emotions students report. Do places marked “unsafe” match buildings with many dark departures?
Time slider: animate dark_by_month to show dark departures growing from October and shrinking in spring.
Worst evenings: use dark_by_weekday and dark_by_end_hour to find the evenings to focus on, for example a walking companion or an extra bus on Tuesdays after 18:00.
Routes home: draw the walk from busy buildings to tram stops, dorms and car parks, and compare it with street-lighting or city open data.
How dark: median_min_after_dusk separates “just after dusk” from “deep night”; use it for colour intensity.
Limits
The numbers describe the timetable of a sample of students, not what actually happened on the street.
Sample, not everyone: the data covers only part of the student body. Compare shares between buildings, not absolute counts with total enrolment.
Missing buildings: buildings below the privacy threshold are left out. A missing building means “few students in the sample”, not “no dark classes”.
Timetable, not attendance: cancelled classes, skipped lectures and people staying late in the library are not visible.
End of class is not leaving time: students may stay longer or leave early.
One dusk for the whole university: calculated for one point. Across one city the difference is seconds; between distant campuses a few minutes.
No weather: overcast days get dark earlier than the calculation says.
Building, not room or exit: everything is per building code; large buildings with several exits look like one point.
Data rules
The dataset contains no names, student numbers or individual timetables, but it is derived from real students' timetables, so please treat it with care.
Use it only for the hackathon project.
Do not try to identify individual students, for example by combining it with other data about specific courses or people.
Do not publish the raw files. Maps and charts built from them are fine.
Delete your copies after the hackathon unless the organisers agree otherwise.
Ask the organisers before joining it with other data that contains personal information.
