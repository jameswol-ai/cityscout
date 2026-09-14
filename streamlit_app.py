"""CityScout Streamlit application entry point."""
from __future__ import annotations
import streamlit as st
st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")
from modules.auth import call_auth_login, create_local_user, ensure_demo_local_user, logout_user, verify_local_user, verify_token
from modules.config import DEFAULT_CATEGORIES, PAGES
from modules.storage import load_user_places
from modules.ui import inject_css, render_logo, sidebar_navigation
from modules.pages import page_add_place, page_ai_cityscout, page_architecture, page_categories, page_dashboard, page_explore, page_places, page_settings, page_share, page_trip_planner
from modules.city_explorer import render_city_explorer
from modules.spatial_dashboard import render_spatial_intelligence
from modules.intelligence import render_city_intelligence
from modules.building_design import render_building_design
from modules.structural_design import render_structural_design
from modules.lateral_design import lateral_summary


def render_lateral_design() -> None:
    from modules.ui import page_header
    import pandas as pd
    page_header("Lateral Design Cockpit")
    st.caption("Conceptual wind, seismic, stability and lateral-system study. Not a code-compliance or final structural design tool.")
    a,b,c=st.columns(3)
    height=a.number_input("Building height (m)",3.0,500.0,30.0,1.0,key="lat_h")
    width=b.number_input("Lateral width (m)",3.0,200.0,30.0,1.0,key="lat_w")
    depth=c.number_input("Lateral depth (m)",3.0,200.0,20.0,1.0,key="lat_d")
    d,e,f=st.columns(3)
    wind=d.number_input("Reference wind speed (m/s)",10.0,80.0,30.0,1.0,key="lat_wind")
    seismic=e.slider("Seismic factor proxy",0.0,1.0,0.10,0.01,key="lat_seis")
    preferred=f.selectbox("Preferred lateral system",["Moment frame","Shear wall core","Braced frame","Dual system"],index=1,key="lat_system")
    result=lateral_summary(height,width,depth,wind,seismic,preferred); action=result["actions"]
    k=st.columns(5)
    k[0].metric("Slenderness",f"{result['selected']['slenderness']:.2f}")
    k[1].metric("Wind pressure",f"{action['wind_pressure_kpa']:.2f} kPa")
    k[2].metric("Base-shear proxy",f"{action['base_shear_proxy']:,.0f}")
    k[3].metric("Drift index",f"{action['drift_index']:.2f}")
    k[4].metric("Selected system",result["selected"]["system"])
    st.subheader("Lateral-system comparison")
    df=pd.DataFrame(result["options"])[["system","description","slenderness","stability_score"]]
    df.columns=["System","Strategy","Slenderness","Stability score"]
    st.dataframe(df.round(2),use_container_width=True,hide_index=True)
    st.bar_chart(df.set_index("System")[["Stability score"]],use_container_width=True)
    st.subheader("Conceptual action indicators")
    st.dataframe(pd.DataFrame([[k,v] for k,v in action.items()],columns=["Indicator","Value"]).round(3),use_container_width=True,hide_index=True)
    st.warning("Wind pressure, base shear and drift values are screening proxies. Final lateral design requires site wind/seismic parameters, massing, diaphragm action, foundation conditions, load combinations and applicable codes.")

PAGE_RENDERERS={"Trip Planner":page_trip_planner,"City Explorer":render_city_explorer,"Spatial Intelligence":render_spatial_intelligence,"City Intelligence":render_city_intelligence,"Architecture & Urban Design":page_architecture,"Building Design Cockpit":render_building_design,"Structural Design Cockpit":render_structural_design,"Lateral Design Cockpit":render_lateral_design,"AI CityScout":page_ai_cityscout,"Dashboard":page_dashboard,"Explore":page_explore,"Add Place":page_add_place,"Places":page_places,"Share":page_share,"Categories":page_categories,"Settings":page_settings}

def initialize_session()->None:
    defaults={"access_token":None,"username":None,"places":[],"categories":list(DEFAULT_CATEGORIES),"auth_mode":None,"page":PAGES[0] if PAGES else "Trip Planner","last_route":None,"trip_templates":{},"share_tokens":{},"explore_results":[],"ai_cityscout_history":[]}
    for key,value in defaults.items():
        if key not in st.session_state: st.session_state[key]=value

def load_current_user_places()->None:
    username=st.session_state.get("username")
    if not username: st.session_state.places=[]; return
    loaded=load_user_places(username); st.session_state.places=loaded if isinstance(loaded,list) else []

def authenticate(username:str,password:str)->bool:
    if not username or not password:return False
    token=call_auth_login(username,password)
    if token:
        info=verify_token(token)
        if info and info.get("username")==username:
            st.session_state.access_token,st.session_state.username,st.session_state.auth_mode=token,username,"remote"; load_current_user_places(); return True
    if verify_local_user(username,password):
        st.session_state.access_token,st.session_state.username,st.session_state.auth_mode=None,username,"local"; load_current_user_places(); return True
    return False

def render_login()->None:
    inject_css(); render_logo(); st.markdown("<div class='small-muted'>Sign in or create an account to continue</div>",unsafe_allow_html=True); ensure_demo_local_user()
    username=st.text_input("Username",key="login_user",placeholder="username"); password=st.text_input("Password",type="password",key="login_pass",placeholder="password")
    login_col,signup_col=st.columns(2)
    with login_col:
        if st.button("Login",use_container_width=True,key="login_submit"):
            if authenticate(username.strip(),password): st.rerun()
            st.error("Login failed. Check your credentials.")
    with signup_col:
        if st.button("Sign up",use_container_width=True,key="signup_submit"):
            clean_username=username.strip()
            if not clean_username or not password: st.error("Enter a username and password."); return
            if create_local_user(clean_username,password): st.session_state.username,st.session_state.access_token,st.session_state.auth_mode,st.session_state.places=clean_username,None,"local",[]; st.rerun()
            st.error("Sign up failed. Username may already exist.")
    st.caption("Demo account: demo / demo123")

def validate_session()->bool:
    username,token=st.session_state.get("username"),st.session_state.get("access_token")
    if not username:return False
    if token:
        info=verify_token(token)
        if not info or info.get("username")!=username: logout_user(); return False
    return True

def render_app()->None:
    inject_css(); sidebar_navigation()
    if st.sidebar.button("Logout",key="sidebar_logout"): logout_user(); st.rerun()
    load_current_user_places(); page=st.session_state.get("page")
    if page not in PAGE_RENDERERS: st.session_state.page=PAGES[0] if PAGES else "Trip Planner"; page=st.session_state.page; st.warning("The selected page is unavailable. Returning to Trip Planner.")
    PAGE_RENDERERS.get(page,page_trip_planner)()

def run()->None:
    initialize_session()
    if not validate_session(): render_login(); return
    render_app()

if __name__=="__main__": run()
