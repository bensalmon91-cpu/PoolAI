from pooldash_app import create_app

app = create_app()

if __name__ == "__main__":
    # Bind to all interfaces, port 80 (direct access, no nginx needed)
    app.run(host="0.0.0.0", port=80, debug=False)
