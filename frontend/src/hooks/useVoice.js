import { useEffect, useState } from "react";
import { voiceClient } from "@/lib/voiceClient";

export function useVoice() {
  const [state, setState] = useState(voiceClient.state);
  useEffect(() => voiceClient.subscribe(setState), []);
  return state;
}
