import { useState, useEffect } from "react";

const API_URL = "/api";

function App() {
  const [items, setItems] = useState([]);
  const [name, setName] = useState("");

  useEffect(() => {
    fetchItems();
  }, []);

  const fetchItems = async () => {
    const res = await fetch(`${API_URL}/items`);
    const data = await res.json();
    setItems(data);
  };

  const addItem = async (e) => {
    e.preventDefault();
    await fetch(`${API_URL}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, description: "Added via UI" }),
    });
    setName("");
    fetchItems();
  };

  const deleteItem = async (id) => {
    await fetch(`${API_URL}/items/${id}`, { method: "DELETE" });
    fetchItems();
  };

  return (
    <div style={{ maxWidth: "600px", margin: "40px auto", fontFamily: "sans-serif" }}>
      <h1>Dodo Payments — Items</h1>

      <form onSubmit={addItem}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Enter item name"
          style={{ padding: "8px", width: "300px" }}
        />
        <button type="submit" style={{ padding: "8px 16px", marginLeft: "8px" }}>
          Add
        </button>
      </form>

      <ul style={{ marginTop: "24px" }}>
        {items.map((item) => (
          <li key={item.id} style={{ marginBottom: "8px" }}>
            <strong>{item.name}</strong> — {item.description}
            <button
              onClick={() => deleteItem(item.id)}
              style={{ marginLeft: "12px", color: "red" }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default App;
