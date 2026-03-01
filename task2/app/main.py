from fastapi import FastAPI

app = FastAPI()

todos = {}
next_id = 1


@app.get("/todos")
def get_all():
    return todos


@app.post("/todos/{title}")
def create(title: str):
    global next_id
    todos[next_id] = title
    next_id += 1
    return f"Todo '{title}' created"


@app.put("/todos/{todo_id}/{title}")
def update(todo_id: int, title: str):
    if todo_id not in todos:
        return "Todo not found"
    todos[todo_id] = title
    return f"Todo {todo_id} updated to '{title}'"


@app.delete("/todos/{todo_id}")
def delete(todo_id: int):
    if todo_id not in todos:
        return "Todo not found"
    del todos[todo_id]
    return f"Todo {todo_id} deleted"
