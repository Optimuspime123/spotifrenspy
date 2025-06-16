
# Spotify Friend Activity Viewer (spy on your spotify frens!)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

A modern, multi-user web application that replicates the "Friend Activity" sidebar from the Spotify desktop client, making it accessible on any web browser. Built with a stateless Flask backend and a dynamic, responsive frontend using Material Design for Bootstrap.


## ✨ Features

-   **View Friend Activity**: See what your friends are listening to in near real-time.
-   **Modern UI**: Clean, responsive interface built with Material Design for Bootstrap.
-   **Light & Dark Modes**: A theme toggle that respects user's OS preference and saves their choice.
-   **Secure & Private**: Your `sp_dc` cookie is stored *only* in your browser's local storage and is never saved on the server.
-   **Multi-User Ready**: The stateless backend architecture ensures that multiple users can use the service simultaneously without any data overlap.
-   **Easy Deployment**: One-click deployment to Render using the included `render.yaml` blueprint.

## 🚀 Live Demo

You can deploy your own version to see it live!
**[spotifrenspy.onrender.com](https://spotifrenspy.onrender.com)**

## 🔧 Technology Stack

-   **Backend**: Python, Flask, Gunicorn
-   **Frontend**: HTML, CSS, JavaScript (Vanilla)
-   **UI Library**: MDB (Material Design for Bootstrap)
-   **Core Dependencies**: Requests, pyotp
-   **Deployment**: Render

---

## ⚙️ Setup and Installation (Local Development)

To run this project on your local machine, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Optimuspime123/spotifrenspy.git
    cd spotify-activity-viewer
    ```

2.  **Create and activate a virtual environment:**
    - On macOS/Linux:
      ```bash
      python3 -m venv venv
      source venv/bin/activate
      ```
    - On Windows:
      ```bash
      python -m venv venv
      .\venv\Scripts\activate
      ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the Flask development server:**
    ```bash
    python app.py
    ```

5.  **Open your browser** and navigate to `http://127.0.0.1:5001`.

---

## ☁️ Deployment to Render

This project is pre-configured for easy deployment on Render using the `render.yaml` file.

1.  **Push your code** to a GitHub repository.
2.  Go to the [Render Dashboard](https://dashboard.render.com/) and create a **New Web Service**.
3.  **Connect the GitHub repository** you just created. (you can technically use this repo url as well)
4.  Render will automatically detect the `render.yaml` file and configure the service.
5.  Click **Create** and wait for the deployment to finish. Your app will be live!

Because `autoDeploy: yes` is enabled, Render will automatically redeploy your app every time you push a new commit to your `main` branch.

---

## 💡 How to Use the App

The app requires a Spotify authentication token called `sp_dc` to fetch your friend activity.

### What is `sp_dc` and how do I get it?

The `sp_dc` cookie is a long-term authentication token that proves you are logged into Spotify. This site uses it to make an authorized request for your friend feed, just like the official app does. Your cookie is only stored in your own browser and is never saved on our server. It typically lasts for several months, or even up to a year.

**Step 1:** Log in to [open.spotify.com](https://open.spotify.com) in a desktop web browser (like Chrome, Firefox, or Edge).

**Step 2:** Get the cookie using one of these methods:

#### Method A: Browser Developer Tools (Recommended)

1.  Press <kbd>F12</kbd> or <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>I</kbd> (Windows) / <kbd>Cmd</kbd>+<kbd>Opt</kbd>+<kbd>I</kbd> (Mac) to open Developer Tools.
2.  Go to the **Application** tab (in Chrome/Edge) or **Storage** tab (in Firefox).
3.  On the left sidebar, expand the "Cookies" section and select `https://open.spotify.com`.
4.  Find the cookie named `sp_dc` in the list.
5.  Double-click on its "Cookie Value" to select it, then copy the entire long string of text.
6.  Paste this value into the input box on the website.

#### Method B: Using a Browser Extension

1.  Install a trusted cookie editor extension (e.g., "Cookie Editor" for Chrome/Firefox).
2.  With the `open.spotify.com` tab active, click the extension's icon in your toolbar.
3.  Find the cookie named `sp_dc` and copy its value.

## ⚠️ Disclaimer

This is a third-party project and is not affiliated with, endorsed, or sponsored by Spotify. The functionality relies on unofficial Spotify APIs which may change or break at any time without notice. Use at your own risk.

## 📄 License

This project is distributed under the MIT License. See the `LICENSE` file for more information.
