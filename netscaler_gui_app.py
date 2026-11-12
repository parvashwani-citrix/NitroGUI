
import streamlit as st
import requests
import pandas as pd
import urllib3
import ssl
from requests.adapters import HTTPAdapter

# Disable insecure request warning for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Custom HTTP Adapter to force TLSv1.2 and support legacy ciphers
class TLSAdapter(HTTPAdapter):
    def __init__(self, ssl_version=None, **kwargs):
        self.ssl_version = ssl_version
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        ciphers = (
            "DEFAULT:@SECLEVEL=1:"
            "ECDHE-ECDSA-AES128-GCM-SHA256:"
            "ECDHE-RSA-AES128-GCM-SHA256:"
            "ECDHE-ECDSA-AES256-GCM-SHA384:"
            "ECDHE-RSA-AES256-GCM-SHA384:"
            "DHE-RSA-AES128-GCM-SHA256:"
            "DHE-RSA-AES256-GCM-SHA384:"
            "ECDHE-ECDSA-AES128-SHA256:"
            "ECDHE-RSA-AES128-SHA256:"
            "ECDHE-ECDSA-AES256-SHA384:"
            "ECDHE-RSA-AES256-SHA384:"
            "DHE-RSA-AES128-SHA256:"
            "DHE-RSA-AES256-SHA256:"
            "AES128-GCM-SHA256:"
            "AES256-GCM-SHA384:"
            "AES128-SHA256:"
            "AES256-SHA256:"
            "ECDHE-ECDSA-AES128-SHA:"
            "ECDHE-RSA-AES128-SHA:"
            "ECDHE-ECDSA-AES256-SHA:"
            "ECDHE-RSA-AES256-SHA:"
            "DHE-RSA-AES128-SHA:"
            "DHE-RSA-AES256-SHA:"
            "AES128-SHA:"
            "AES256-SHA:"
            "DES-CBC3-SHA"
        )
        try:
            ctx.set_ciphers(ciphers)
        except ssl.SSLError:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
            
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

st.set_page_config(
    page_title="NetScaler Console - Modern GUI",
    page_icon="⚡",
    layout="wide",
)

# Custom CSS for Citrix-like Branding
st.markdown("""
    <style>
    .main-header {
        background-color: #002F6C;
        padding: 15px;
        border-radius: 8px;
        color: white;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: #F0F4F8;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #002F6C;
        margin-bottom: 10px;
    }
    .status-up {
        color: #2E7D32;
        font-weight: bold;
    }
    .status-down {
        color: #C62828;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-header'><h1>⚡ NetScaler Appliance Control Panel</h1><p>Modern Alternative Web Console powered by NITRO REST API</p></div>", unsafe_allow_html=True)

# Sidebar Configuration
st.sidebar.header("🔌 Connection settings")
ns_ip = st.sidebar.text_input("NetScaler IP (NSIP)", value="10.14.12.103")
ns_username = st.sidebar.text_input("Username", value="nsroot")
ns_password = st.sidebar.text_input("Password", type="password", value="Parv@4321")
use_http = st.sidebar.checkbox("Use HTTP (Port 80)", value=False)

if "nitro_token" not in st.session_state:
    st.session_state.nitro_token = None
if "connected" not in st.session_state:
    st.session_state.connected = False

def get_session():
    session = requests.Session()
    adapter = TLSAdapter()
    session.mount("https://", adapter)
    return session

def nitro_request(method, ip, resource, payload=None, http_fallback=False):
    protocol = "http" if http_fallback else "https"
    url = f"{protocol}://{ip}/nitro/v1/config/{resource}"
    
    # Strictly avoid sending X-NITRO-USER/PASS on the 'login' endpoint to prevent errorcode 1025
    headers = {
        "Content-Type": "application/json"
    }
    
    if resource != "login":
        if st.session_state.nitro_token:
            headers["Cookie"] = f"NITRO_AUTH_TOKEN={st.session_state.nitro_token}; sessionid={st.session_state.nitro_token}"
        else:
            headers["X-NITRO-USER"] = ns_username
            headers["X-NITRO-PASS"] = ns_password
    
    session = get_session()
    try:
        if method.upper() == "GET":
            response = session.get(url, headers=headers, verify=False, timeout=5)
        elif method.upper() == "POST":
            response = session.post(url, json=payload, headers=headers, verify=False, timeout=5)
        elif method.upper() == "PUT":
            response = session.put(url, json=payload, headers=headers, verify=False, timeout=5)
        elif method.upper() == "DELETE":
            response = session.delete(url, headers=headers, verify=False, timeout=5)
            
        # Parse Response Safely
        if response.status_code in [200, 201]:
            cookie_token = response.cookies.get("NITRO_AUTH_TOKEN") or response.cookies.get("sessionid")
            
            if not response.text.strip():
                return {"sessionid": cookie_token} if cookie_token else {"status": "success"}, None
            
            try:
                data = response.json()
                if cookie_token and "sessionid" not in data:
                    data["sessionid"] = cookie_token
                return data, None
            except ValueError:
                if cookie_token:
                    return {"sessionid": cookie_token, "raw_text": response.text}, None
                return None, f"Received non-JSON response: {response.text[:200]}"
        else:
            return None, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return None, str(e)

# Connect Buttons
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("Connect", use_container_width=True):
        with st.spinner("Logging in..."):
            login_url = "login"
            payload = {"login": {"username": ns_username, "password": ns_password}}
            res, err = nitro_request("POST", ns_ip, login_url, payload, use_http)
            if res is not None and not err:
                token = res.get("sessionid") or res.get("login", {}).get("sessionid")
                if not token and "login" in res and isinstance(res["login"], dict):
                    token = res["login"].get("sessionid")
                
                st.session_state.nitro_token = token
                st.session_state.connected = True
                st.sidebar.success("Connected!")
            else:
                st.session_state.connected = False
                st.sidebar.error(f"Login failed: {err}")
with col2:
    if st.button("Disconnect", use_container_width=True):
        st.session_state.nitro_token = None
        st.session_state.connected = False
        st.sidebar.info("Disconnected")

if st.session_state.connected:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard & Hardware", 
        "🌐 Virtual Servers (LB/CS)", 
        "⚙️ Core Configurations",
        "🛠️ System Settings & Features",
        "📂 Diagnostic Terminal"
    ])
    
    # ---------------- TAB 1: DASHBOARD & HARDWARE ----------------
    with tab1:
        st.subheader("System Live Status Overview")
        
        nsip_data, err_nsip = nitro_request("GET", ns_ip, "nsip", http_fallback=use_http)
        hw_data, err_hw = nitro_request("GET", ns_ip, "nshardware", http_fallback=use_http)
        
        if nsip_data and "nsip" in nsip_data:
            info = nsip_data["nsip"][0] if isinstance(nsip_data["nsip"], list) else nsip_data["nsip"]
            
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric(label="Appliance IP Address (NSIP)", value=info.get("ipaddress", "N/A"))
            with m_col2:
                st.metric(label="Netmask", value=info.get("netmask", "N/A"))
            with m_col3:
                st.metric(label="Free Ports Available", value=f"{int(info.get('freeports', 0)):,}" if info.get('freeports') else "N/A")
            with m_col4:
                status = info.get("state", "UNKNOWN")
                st.metric(label="System Status", value=status)
                
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.markdown("### 🖥️ Management Protocols")
                st.write(f"**SSH:** {info.get('ssh', 'N/A')} | **GUI:** {info.get('gui', 'N/A')} | **Telnet:** {info.get('telnet', 'N/A')}")
                st.write(f"**FTP:** {info.get('ftp', 'N/A')} | **SNMP:** {info.get('snmp', 'N/A')} | **Management Access:** {info.get('mgmtaccess', 'N/A')}")
                st.write(f"**Dynamic Routing:** {info.get('dynamicrouting', 'N/A')} | **ARP:** {info.get('arp', 'N/A')}")
            with g_col2:
                if hw_data and "nshardware" in hw_data:
                    hw = hw_data["nshardware"]
                    st.markdown("### ⚙️ Hardware Specifications")
                    st.write(f"**Model Description:** {hw.get('hwdescription', 'N/A')}")
                    st.write(f"**Serial Number:** `{hw.get('serialno', 'N/A')}`")
                    st.write(f"**CPU Speed:** {hw.get('cpufrequncy', 'N/A')} MHz")
                    st.write(f"**UUID:** `{hw.get('netscaleruuid', 'N/A')}`")
                    st.write(f"**Manufacture Date:** {hw.get('manufactureday', 'N/A')}/{hw.get('manufacturemonth', 'N/A')}/{hw.get('manufactureyear', 'N/A')}")
        else:
            st.error(f"Could not parse system IP status info: {err_nsip}")

    # ---------------- TAB 2: VIRTUAL SERVERS ----------------
    with tab2:
        st.subheader("Manage Virtual Servers")
        v_sub1, v_sub2 = st.tabs(["Load Balancing VServers", "Content Switching VServers"])
        
        with v_sub1:
            lb_data, err_lb = nitro_request("GET", ns_ip, "lbvserver", http_fallback=use_http)
            if lb_data and "lbvserver" in lb_data:
                df = pd.DataFrame(lb_data["lbvserver"])
                cols = [c for c in ["name", "servicetype", "ipv46", "port", "curstate", "effectivestate"] if c in df.columns]
                st.dataframe(df[cols], use_container_width=True)
            else:
                st.info("No Load Balancing Virtual Servers found.")
                
            with st.expander("➕ Add New Load Balancing Virtual Server"):
                with st.form("create_lb"):
                    lb_name = st.text_input("VServer Name")
                    lb_proto = st.selectbox("Protocol", ["HTTP", "SSL", "TCP", "UDP"])
                    lb_ip = st.text_input("IP Address")
                    lb_port = st.number_input("Port", min_value=1, max_value=65535, value=80)
                    submit_lb = st.form_submit_button("Create LB VServer")
                    if submit_lb:
                        payload = {"lbvserver": {"name": lb_name, "servicetype": lb_proto, "ipv46": lb_ip, "port": int(lb_port)}}
                        res, err = nitro_request("POST", ns_ip, "lbvserver", payload, use_http)
                        if err:
                            st.error(f"Error creating VServer: {err}")
                        else:
                            st.success(f"VServer {lb_name} created successfully!")
                            st.rerun()

        with v_sub2:
            cs_data, err_cs = nitro_request("GET", ns_ip, "csvserver", http_fallback=use_http)
            if cs_data and "csvserver" in cs_data:
                df_cs = pd.DataFrame(cs_data["csvserver"])
                cols = [c for c in ["name", "servicetype", "ipv46", "port", "curstate"] if c in df_cs.columns]
                st.dataframe(df_cs[cols], use_container_width=True)
            else:
                st.info("No Content Switching Virtual Servers found.")

    # ---------------- TAB 3: CORE CONFIGURATIONS ----------------
    with tab3:
        st.subheader("Core Services & Service Groups")
        c_sub1, c_sub2 = st.tabs(["Services", "Backend Servers"])
        
        with c_sub1:
            svc_data, err_svc = nitro_request("GET", ns_ip, "service", http_fallback=use_http)
            if svc_data and "service" in svc_data:
                df_svc = pd.DataFrame(svc_data["service"])
                cols = [c for c in ["name", "servicetype", "port", "curstate"] if c in df_svc.columns]
                st.dataframe(df_svc[cols], use_container_width=True)
            else:
                st.info("No Services found.")
                
        with c_sub2:
            srv_data, err_srv = nitro_request("GET", ns_ip, "server", http_fallback=use_http)
            if srv_data and "server" in srv_data:
                df_srv = pd.DataFrame(srv_data["server"])
                cols = [c for c in ["name", "ipaddress", "state"] if c in df_srv.columns]
                st.dataframe(df_srv[cols], use_container_width=True)
            else:
                st.info("No Backend Servers found.")
                
            with st.expander("➕ Add New Backend Server"):
                with st.form("create_srv"):
                    srv_name = st.text_input("Server Name")
                    srv_ip = st.text_input("Server IP Address")
                    submit_srv = st.form_submit_button("Add Server")
                    if submit_srv:
                        payload = {"server": {"name": srv_name, "ipaddress": srv_ip}}
                        res, err = nitro_request("POST", ns_ip, "server", payload, use_http)
                        if err:
                            st.error(f"Error adding server: {err}")
                        else:
                            st.success(f"Server {srv_name} added successfully!")
                            st.rerun()

    # ---------------- TAB 4: SYSTEM SETTINGS & FEATURES ----------------
    with tab4:
        st.subheader("Manage NetScaler Appliance Features")
        
        features, err_feat = nitro_request("GET", ns_ip, "nsfeature", http_fallback=use_http)
        if features and "nsfeature" in features:
            f_data = features["nsfeature"]
            
            st.markdown("### Active Features Check:")
            cols = st.columns(3)
            # Filter out non-boolean metadata keys like 'feature' list
            valid_features = {k: v for k, v in f_data.items() if isinstance(v, bool) or v in ["ENABLED", "DISABLED"]}
            for i, (key, value) in enumerate(valid_features.items()):
                col = cols[i % 3]
                is_enabled = (value is True) or (value == "ENABLED")
                
                status_emoji = "🟢 Enabled" if is_enabled else "🔴 Disabled"
                col.write(f"**{key.upper()}:** {status_emoji}")
                
                button_label = f"Disable {key.upper()}" if is_enabled else f"Enable {key.upper()}"
                if col.button(button_label, key=f"btn_{key}"):
                    payload = {"nsfeature": {"feature": [key]}}
                    res, err = nitro_request("POST", ns_ip, f"nsfeature?action={'disable' if is_enabled else 'enable'}", payload, use_http)
                    if err:
                        st.error(f"Failed to change {key} status: {err}")
                    else:
                        st.success(f"Feature {key.upper()} updated successfully!")
                        st.rerun()
        else:
            st.warning("Could not retrieve appliance feature settings.")

    # ---------------- TAB 5: DIAGNOSTICS & RAW UTILITIES ----------------
    with tab5:
        st.subheader("Diagnostics & RAW Utility Engine")
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            st.markdown("### System Utility Operations")
            if st.button("💾 Save Running Configuration", use_container_width=True):
                payload = {"nsconfig": {}}
                res, err = nitro_request("POST", ns_ip, "nsconfig?action=save", payload, use_http)
                if err:
                    st.error(f"Failed to save configuration: {err}")
                else:
                    st.success("Configuration successfully saved.")
            
            if st.button("🔄 Reboot Appliance", use_container_width=True):
                st.warning("Are you sure you want to reboot?")
                if st.button("⚠️ Confirm Reboot now"):
                    payload = {"reboot": {"warm": True}}
                    res, err = nitro_request("POST", ns_ip, "reboot", payload, use_http)
                    if err:
                        st.error(f"Reboot command failed: {err}")
                    else:
                        st.success("Reboot command sent successfully.")

        with col_act2:
            st.markdown("### Direct Endpoint Query")
            custom_endpoint = st.text_input("Resource Name (e.g. 'nshostname' or 'nsmode')", "nshostname")
            if st.button("Query API Resource", use_container_width=True):
                res, err = nitro_request("GET", ns_ip, custom_endpoint, http_fallback=use_http)
                if err:
                    st.error(f"Query failed: {err}")
                else:
                    st.json(res)

else:
    st.info("💡 Please specify your connection credentials on the left sidebar and click **Connect** to initialize the NetScaler Web Console.")
