from flask import Flask as fk, jsonify, request

app = fk(__name__)

@app.route("/")
def root():
    return "root"

if __name__ == '__main__':
    app.run(debug=True)