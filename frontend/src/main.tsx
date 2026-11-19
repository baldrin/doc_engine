import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import Activity from "./Activity";
import Builder from "./Builder";
import Files from "./Files";
import Flows from "./Flows";
import { usePath } from "./lib";
import Results from "./Results";
import Run from "./Run";
import { Link, ToastHost } from "./ui";

function App() {
  const path = usePath();
  let screen;
  let m: RegExpMatchArray | null;
  if (path === "/" || path === "/flows") screen = <Flows />;
  else if ((m = path.match(/^\/flows\/([^/]+)$/))) screen = <Builder key={m[1]} flowId={m[1]} />;
  else if ((m = path.match(/^\/runs\/([^/]+)\/results$/))) screen = <Results key={m[1]} jobId={m[1]} />;
  else if ((m = path.match(/^\/runs\/([^/]+)$/))) screen = <Run key={m[1]} jobId={m[1]} />;
  else if (path === "/activity") screen = <Activity />;
  else if (path === "/files") screen = <Files />;
  else screen = <div className="page"><h1>Page not found</h1><Link to="/">Back to flows</Link></div>;
  return <>{screen}<ToastHost /></>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
