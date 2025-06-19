import streamlit as st
from openai import OpenAI
import openai
import re
import os

# Load API key from environment variable
openai_api_key = os.getenv("OPENAI_API_KEY")

if not openai_api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")

client = openai.OpenAI(api_key=openai_api_key)

st.set_page_config(layout="wide")
st.markdown("## 🤝 Buyer / Procurement Support Agent")

# Custom CSS for chat alignment and price display
st.markdown("""
<style>
.vendor-message {
    background-color: #f0f2f6;
    padding: 10px;
    border-radius: 10px;
    margin: 10px 0;
    border-left: 4px solid #ff6b35;
}

.buyer-message {
    background-color: #e8f4fd;
    padding: 10px;
    border-radius: 10px;
    margin: 10px 0;
    margin-left: 20%;
    border-right: 4px solid #1f77b4;
    text-align: right;
}

.ai-suggestion {
    background-color: #f8f9fa;
    padding: 10px;
    border-radius: 10px;
    margin: 10px 0;
    border-left: 4px solid #28a745;
}

.price-banner {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 15px;
    border-radius: 10px;
    margin: 10px 0;
    text-align: center;
    font-weight: bold;
}

.current-offer {
    background-color: #ffeaa7;
    padding: 10px;
    border-radius: 8px;
    margin: 5px 0;
    border-left: 4px solid #fdcb6e;
}
</style>
""", unsafe_allow_html=True)

# Define brand and product mapping with sample prices
BRAND_PRODUCTS = {
    "Apple": {
        "MacBook": 1500,
        "iMac": 1800,
        "iPad": 600,
        "iPhone": 1000,
        "Accessories": 100
    },
    "Microsoft": {
        "Surface": 1300,
        "Office 365": 150,
        "Azure Services": 500,
        "Teams License": 80,
        "Windows License": 200
    },
    "P&G": {
        "Detergent": 12, 
        "Shampoo" : 3, 
        "Toothpaste" : 1.50, 
        "Shavers" : 80, 
        "Cleaning Products" : 4 
        },
    "Unilever": {
        "Soap": 0.80, 
        "Ice Cream" : 3.50,
        "Tea" : 3,
        "Personal Care": 2,
        "Household Products": 2.50
        }
}

# Initialize session state variables
if 'chat3_history' not in st.session_state:
    st.session_state.chat3_history = [
        {"role": "system", "content": (
            "You are an AI negotiation strategist. The chat involves a buyer and a vendor. "
            "Your job is to analyze the conversation and occasionally provide strategic suggestions "
            "to the buyer to improve negotiation outcomes."
        )}
    ]

if 'draft_strategy' not in st.session_state:
    st.session_state.draft_strategy = None

if 'draft_buyer_message' not in st.session_state:
    st.session_state.draft_buyer_message = None

if 'vendor_auto_responded' not in st.session_state:
    st.session_state.vendor_auto_responded = False

if 'negotiation_started' not in st.session_state:
    st.session_state.negotiation_started = False

if 'market_insights' not in st.session_state:
    st.session_state.market_insights = None

if 'current_vendor_offer' not in st.session_state:
    st.session_state.current_vendor_offer = None

# Reset function that properly clears session state
def reset_app():
    keys_to_keep = ['chat3_history', 'draft_strategy', 'draft_buyer_message']
    for key in list(st.session_state.keys()):
        if key not in keys_to_keep:
            del st.session_state[key]
    st.session_state.chat3_history = st.session_state.chat3_history[:1]  # Keep only system message
    st.session_state.draft_strategy = None
    st.session_state.draft_buyer_message = None
    st.session_state.vendor_auto_responded = False
    st.session_state.negotiation_started = False
    st.session_state.market_insights = None
    st.session_state.current_vendor_offer = None

# Function to extract price from vendor message
def extract_price_from_message(message):
    # Look for price patterns like $1200, $1,200, $1200.00, 1050, etc.
    price_patterns = [
        r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $1200, $1,200, $1200.00
        r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*dollars?',  # 1200 dollars, 1,200 dollars
        r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD',  # 1200 USD, 1,200 USD
        r'(?:^|\s)(\d{3,}(?:,\d{3})*(?:\.\d{2})?)(?=\s|$|[^\d])',  # Standalone numbers 3+ digits
    ]
    
    for pattern in price_patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        if matches:
            # Return the first match, removing commas and converting to float
            try:
                price_str = matches[0].replace(',', '')
                price_val = float(price_str)
                # Filter out unrealistic prices (too small or too large)
                if 1 <= price_val <= 1000000:  # Reasonable price range
                    return price_val
            except:
                continue
    return None

# Function to generate vendor's initial quote
def generate_vendor_quote(vendor, product, quoted_price):
    vendor_prompt = f"""
    You are a sales representative working for {vendor}. A potential buyer wants to discuss purchasing {product}.
    
    IMPORTANT: You are speaking AS the {vendor} sales rep, not giving suggestions about what to say.
    
    Respond naturally as a salesperson would in a real conversation. Keep it brief (1-2 sentences).
    Mention the ${quoted_price} price in a natural way.
    
    Example good response: "Hi! Thanks for your interest in our {product}. We're offering it at ${quoted_price} - it's a great value for the quality we provide."
    
    Do NOT say things like "Suggestion:" or "The vendor could say:" - just speak as the vendor directly.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": vendor_prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Hi! I can offer you our {product} for ${quoted_price}. Great quality at a competitive price."

# Function to generate vendor's response to buyer
def generate_vendor_response(chat_history, vendor, product, quoted_price, buyer_message):
    # Get the last few messages for context
    recent_context = ""
    if len(chat_history) > 1:
        recent_messages = chat_history[-3:]
        for msg in recent_messages:
            if msg["content"].startswith("Buyer:"):
                recent_context += f"Buyer said: {msg['content'][7:]}\n"
            elif msg["content"].startswith(f"Vendor ({vendor}):"):
                recent_context += f"You (vendor) said: {msg['content'][len(f'Vendor ({vendor}): '):]}\n"
    
    vendor_context = f"""
    You are a {vendor} sales representative. You are currently negotiating the sale of {product} with an asking price of ${quoted_price}.
    
    Context of recent conversation:
    {recent_context}
    
    The buyer just said: "{buyer_message}"
    
    IMPORTANT: Respond AS the {vendor} sales rep, not as an advisor giving suggestions.
    
    Guidelines for your response:
    - Keep it conversational and brief (1-2 sentences max)
    - Act like a realistic salesperson who wants to make the sale but also protect profit margins
    - You can negotiate, but don't give away too much too quickly
    - Show some flexibility if the buyer makes reasonable points
    - If you mention a price, be specific (e.g., "I can do $1150" not "I can lower it a bit")
    - Do NOT say "Suggestion:" or "The vendor could say:" - just respond directly as the vendor
    
    Respond naturally as the {vendor} sales rep would in this situation.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": vendor_context}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return "Thanks for that. Let me see what I can do for you."

# Function to display chat messages with proper alignment
def display_chat_message(content, message_type):
    if message_type == "vendor":
        st.markdown(f'<div class="vendor-message">🛍️ {content}</div>', unsafe_allow_html=True)
    elif message_type == "buyer":
        st.markdown(f'<div class="buyer-message">🧑‍💼 {content}</div>', unsafe_allow_html=True)
    elif message_type == "ai_suggestion":
        st.markdown(f'<div class="ai-suggestion">🧠 {content}</div>', unsafe_allow_html=True)

# Define three-column layout
col1, col2, col3 = st.columns([1, 1.6, 1])

# ---- LEFT PANEL: Inputs ----
with col1:
    st.markdown("### 📊 Vendor & Product Details")
    st.markdown("*Complete all selections to start negotiation*")

    # Add reset button at the top
    if st.button("🔄 Reset All Selections", type="secondary"):
        reset_app()
        st.rerun()

    # Brand dropdown
    vendor = st.selectbox(
        "Supplier/Vendor",
        options=["Select Brand"] + list(BRAND_PRODUCTS.keys()),
        index=0,
        key="vendor_select"
    )

    # Product dropdown - dynamically updates based on vendor
    if vendor == "Select Brand":
        product = st.selectbox(
            "Product Category",
            options=["Select Product"],
            index=0,
            disabled=True,
            key="product_select"
        )
        quoted_price = st.number_input(
            "Quoted Price ($)",
            min_value=0.0,
            value=0.0,
            step=50.0,
            disabled=True,
            key="quoted_price_input"
        )
        selections_complete = False
    else:
        product = st.selectbox(
            "Product Category",
            options=["Select Product"] + list(BRAND_PRODUCTS[vendor].keys()),
            index=0,
            key="product_select"
        )
        
        if product == "Select Product":
            quoted_price = st.number_input(
                "Quoted Price ($)",
                min_value=0.0,
                value=0.0,
                step=50.0,
                disabled=True,
                key="quoted_price_input"
            )
            selections_complete = False
        else:
            quoted_price = st.number_input(
                "Quoted Price ($)",
                min_value=0.0,
                value=float(BRAND_PRODUCTS[vendor][product]),
                step=50.0,
                key="quoted_price_input"
            )
            selections_complete = True

    # Show completion status
    if selections_complete:
        st.success("✅ All selections complete!")
    else:
        st.warning("⚠️ Please complete all selections above")

    # Insight options
    include_brief = st.checkbox("📄 Market Intelligence Brief", value=True)
    include_rates = st.checkbox("📈 Current Market Rates", value=True)
    include_purchases = st.checkbox("📦 Our Previous Purchases with Vendor", value=True)
    include_competitors = st.checkbox("⚖️ Competitor Comparison", value=True)

    generate_button = st.button(
        "🚀 Generate Insights", 
        disabled=not selections_complete,
        type="primary"
    )

# ---- CENTER PANEL: Price Banner + Chat + Summary ----
with col2:
    # Price Banner at the top
    if selections_complete and st.session_state.negotiation_started:
        st.markdown(f"""
        <div class="price-banner">
            📊 Initial Quote: ${quoted_price} | Product: {product} | Vendor: {vendor}
        </div>
        """, unsafe_allow_html=True)
        
        # Show current vendor offer if it exists and is different from initial
        if st.session_state.current_vendor_offer and st.session_state.current_vendor_offer != quoted_price:
            st.markdown(f"""
            <div class="current-offer">
                💰 Current Vendor Offer: ${st.session_state.current_vendor_offer}
            </div>
            """, unsafe_allow_html=True)
    
    # st.divider()
    st.subheader("💬 Negotiation Chat")
    
    if not selections_complete:
        st.info("👈 Please complete your selections in the left panel to start negotiating")
        st.markdown("**Steps:**")
        st.markdown("1. Select a Supplier/Vendor")
        st.markdown("2. Choose a Product Category") 
        st.markdown("3. Review/Adjust the Quoted Price")
        st.markdown("4. Click 'Generate Market Insights & Start Negotiation'")
    else:
        # Auto-generate vendor quote when insights are generated
        if generate_button and not st.session_state.vendor_auto_responded:
            vendor_quote = generate_vendor_quote(vendor, product, quoted_price)
            vendor_msg = f"Vendor ({vendor}): {vendor_quote}"
            st.session_state.chat3_history.append({"role": "assistant", "content": vendor_msg})
            st.session_state.vendor_auto_responded = True
            st.session_state.negotiation_started = True
            # Set initial vendor offer
            st.session_state.current_vendor_offer = quoted_price

        if st.session_state.negotiation_started:
            # --- Chat Form - Only for Buyer ---
            with st.form("chat_form", clear_on_submit=True):
                buyer_input = st.text_input("🧑‍💼 Your response as Buyer:", key="buyer_input_form")
                submitted = st.form_submit_button("Send Message")

            if submitted and buyer_input:
                # Add buyer message
                buyer_msg = f"Buyer: {buyer_input}"
                st.session_state.chat3_history.append({"role": "user", "content": buyer_msg})
                
                # Generate vendor response
                vendor_response = generate_vendor_response(
                    st.session_state.chat3_history, vendor, product, quoted_price, buyer_input
                )
                vendor_msg = f"Vendor ({vendor}): {vendor_response}"
                st.session_state.chat3_history.append({"role": "assistant", "content": vendor_msg})
                
                # Extract and update current vendor offer if a new price is mentioned
                new_price = extract_price_from_message(vendor_response)
                if new_price:
                    st.session_state.current_vendor_offer = new_price
                
                st.rerun()

            # --- Display Chat History with Custom Styling ---
            for msg in st.session_state.chat3_history[1:]:
                if msg["role"] == "user":
                    if msg["content"].startswith("Buyer:"):
                        display_chat_message(msg['content'], "buyer")
                    else:
                        display_chat_message(f"🤝 {msg['content']}", "buyer")
                elif msg["role"] == "assistant":
                    if msg["content"].startswith("Vendor"):
                        display_chat_message(msg['content'], "vendor")
                    else:
                        display_chat_message(f"AI Suggestion: {msg['content']}", "ai_suggestion")

            # --- Strategy Suggestion - Only show if there's recent vendor response ---
            if len(st.session_state.chat3_history) > 1:
                if st.button("💡 Get AI Strategy Suggestion"):
                    strategy_prompt = f"""
                    You are assisting a buyer in negotiation with {vendor} for {product} at ${quoted_price}.

                    Analyze the recent conversation and provide:
                    1. A strategic insight on how the buyer should respond
                    2. A suggested buyer message that is natural and persuasive

                    Recent conversation context:
                    {st.session_state.chat3_history[-3:] if len(st.session_state.chat3_history) >= 3 else st.session_state.chat3_history[1:]}

                    Format your response as:
                    Strategy: <your strategic advice>
                    Message: <your suggested buyer response>
                    """
                    try:
                        ai_response = client.chat.completions.create(
                            model="gpt-4",
                            messages=[{"role": "user", "content": strategy_prompt}],
                            temperature=0.6
                        )
                        full_output = ai_response.choices[0].message.content.strip()

                        # Parse strategy and message
                        if "Strategy:" in full_output and "Message:" in full_output:
                            strategy = full_output.split("Strategy:")[1].split("Message:")[0].strip()
                            message = full_output.split("Message:")[1].strip()
                            
                            st.session_state["draft_strategy"] = strategy
                            st.session_state["draft_buyer_message"] = message
                        else:
                            st.warning("Couldn't parse AI suggestion properly. Please try again.")

                    except Exception as e:
                        st.error(f"Error generating suggestion: {e}")

            # --- Display Strategy + Drafted Buyer Message ---
            if st.session_state["draft_strategy"] and st.session_state["draft_buyer_message"]:
                st.markdown("#### 🤖 AI Strategy Suggestion")
                st.info(st.session_state["draft_strategy"])
                
                with st.expander("📝 Suggested Response", expanded=True):
                    st.markdown(f"**Suggested Message:**")
                    st.markdown(f"_{st.session_state['draft_buyer_message']}_")

                col_respond1, col_respond2 = st.columns(2)
                with col_respond1:
                    if st.button("📨 Send This Response", type="primary"):
                        # Send the AI-suggested message
                        buyer_msg = f"Buyer: {st.session_state['draft_buyer_message']}"
                        st.session_state.chat3_history.append({"role": "user", "content": buyer_msg})
                        
                        # Generate vendor response to AI suggestion
                        vendor_response = generate_vendor_response(
                            st.session_state.chat3_history, vendor, product, quoted_price, 
                            st.session_state['draft_buyer_message']
                        )
                        vendor_msg = f"Vendor ({vendor}): {vendor_response}"
                        st.session_state.chat3_history.append({"role": "assistant", "content": vendor_msg})
                        
                        # Extract and update current vendor offer if a new price is mentioned
                        new_price = extract_price_from_message(vendor_response)
                        if new_price:
                            st.session_state.current_vendor_offer = new_price
                        
                        # Clear suggestions
                        st.session_state["draft_strategy"] = None
                        st.session_state["draft_buyer_message"] = None
                        st.rerun()
                
                with col_respond2:
                    if st.button("❌ Clear Suggestion"):
                        st.session_state["draft_strategy"] = None
                        st.session_state["draft_buyer_message"] = None
                        st.rerun()

    # --- Post-Negotiation Summary ---
    st.divider()
    st.subheader("🧾 Negotiation Summary")

    if st.session_state.negotiation_started and len(st.session_state.chat3_history) > 2:
        if st.button("📋 Generate Negotiation Summary"):
            # Use the chat history to generate summary
            chat_content = "\n".join([msg["content"] for msg in st.session_state.chat3_history[1:]])
            
            with st.spinner("Summarizing negotiation..."):
                summary_prompt = f"""
                Based on this negotiation between buyer and vendor for {product} from {vendor} (initially quoted at ${quoted_price}), create a structured summary:

                - **Key Discussion Points**
                - **Negotiation Progress** 
                - **Current Status**
                - **Price Movement** (if any)
                - **Next Steps/Action Items**
                - **Strategic Insights**

                Conversation:
                {chat_content}
                """
                try:
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.5
                    )
                    summary = response.choices[0].message.content
                    st.markdown("### 📄 Negotiation Summary")
                    st.markdown(summary)
                except Exception as e:
                    st.error(f"Error generating summary: {e}")
    else:
        st.info("Start negotiating to generate a summary of your conversation")

# ---- RIGHT PANEL: Market Insights ----
with col3:
    # Generate insights only when button is clicked
    if generate_button and selections_complete and not st.session_state.market_insights:
        with st.spinner("Fetching market insights..."):
            prompt = f"""
            You are an expert procurement advisor. Prepare a structured negotiation insights report for a buyer:

            ### Market Intelligence Brief:
            (Provide insights on {product} market trends, {vendor}'s position, and negotiation leverage points)

            ### Current Market Rates:
            Brand | Model | Price Range | Notes
            --- | --- | --- | ---
            (Include 3-4 comparable {product} options with realistic pricing)

            ### Previous Purchases:
            Date | Item | Quantity | Unit Price | Total | OTIF
            --- | --- | --- | ---
            (Generate realistic past purchase data with {vendor})

            ### Competitor Comparison:
            Vendor | Unit Price | Key Advantage | Delivery
            --- | --- | --- | ---
            (Compare {vendor} with 2-3 competitors for {product})

            ### Negotiation Tips:
            (Provide 3-4 specific tactics for negotiating {product} with {vendor})

            Context: {vendor} | {product} | ${quoted_price}
            """
            try:
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4
                )
                st.session_state.market_insights = response.choices[0].message.content
                
            except Exception as e:
                st.error(f"Error generating insights: {e}")
                st.session_state.market_insights = None

    # Display market insights (persistent once generated)
    if st.session_state.market_insights and selections_complete:
        def extract_section(text: str, section: str) -> str:
            pattern = rf"### {re.escape(section)}:\n(.*?)(?=\n###|\Z)"
            match = re.search(pattern, text, re.DOTALL)
            return match.group(1).strip() if match else "No data available."

        st.markdown("### 🧠 Market Insights")
        st.markdown(f"*Analysis for {product} from {vendor}*")
        st.markdown(f"**Initial Quote:** ${quoted_price}")

        if include_brief:
            st.markdown("#### 📄 Market Intelligence Brief")
            st.markdown(extract_section(st.session_state.market_insights, "Market Intelligence Brief"))

        if include_rates:
            st.markdown("#### 📈 Current Market Rates")
            st.markdown(extract_section(st.session_state.market_insights, "Current Market Rates"))

        if include_purchases:
            st.markdown("#### 📦 Previous Purchase History")
            st.markdown(extract_section(st.session_state.market_insights, "Previous Purchases"))

        if include_competitors:
            st.markdown("#### ⚖️ Competitor Comparison")
            st.markdown(extract_section(st.session_state.market_insights, "Competitor Comparison"))
        
        # Always show negotiation tips
        st.markdown("#### 💡 Negotiation Tips")
        st.markdown(extract_section(st.session_state.market_insights, "Negotiation Tips"))
        
    elif not selections_complete:
        st.info("👈 Complete your selections to view market insights")
    else:
        st.markdown("### 🧠 Market Insights")
        st.markdown("*Click 'Generate Market Insights' to view analysis*")
