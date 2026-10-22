import { useEffect } from "react";

/**
 * A plain, neutral white page. Used for rejected/revoked guests and for Guest Screen
 * Hide. This is presentation only; the server enforces authorization and withholds
 * all room/game data from hidden sessions.
 */
export function BlankScreen() {
  useEffect(() => {
    const previous = document.title;
    document.title = "​";
    return () => {
      document.title = previous;
    };
  }, []);
  return <div className="blank-screen" aria-hidden="true" />;
}
