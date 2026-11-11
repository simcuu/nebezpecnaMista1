import streamlit as st

def uloz_data(nazev, problem):
    with open("data.txt", "a") as f:
        f.write(f"Název: {nazev}\n")
        f.write(f"Problém: {problem}\n")
        f.write("\n")

with st.form (key="my_form"):
    nazev = st.text_input("Napište název")
    problem = st.text_input("Svěřte se s problémem")
    submit_button = st.form_submit_button(label="Ano bohužel mám tento problém :/")
    if submit_button:
        uloz_data(nazev, problem)
        st.success("Děkujeme za sdílení vašeho problému!")