import json
import streamlit as st

def uloz_data(misto, problem, denni_doba):
    zaznam = {
        "properties": {
            "misto": misto,
            "problem": problem,
            "denni_doba": denni_doba,
        }
    }
    with open("data.txt", "a", encoding="utf-8") as f:
        json.dump(zaznam, f, ensure_ascii=False)
        f.write("\n")

with st.form (key="my_form"):
    misto = st.text_input("Napište místo, se kterým máte problém.")
    problem = st.text_input("Popište problém, se kterým se na tomto místě potýkáte.")
    denni_doba = st.selectbox("Vyberte denní dobu, kdy se problém vyskytuje.", ["Den","Noc"])
    submit_button = st.form_submit_button(label="Přidejte toto misto na mapu prosím")
    if submit_button:
        uloz_data(misto, problem, denni_doba)
        st.success("Děkujeme za sdílení vašeho problému!")