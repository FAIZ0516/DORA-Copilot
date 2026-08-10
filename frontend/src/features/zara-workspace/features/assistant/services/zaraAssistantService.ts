import type { ZaraAssistantService } from "../types/assistant";
import { MockZaraAssistantService } from "./mockZaraAssistantService";
import { RealZaraAssistantService } from "./realZaraAssistantService";

export const zaraAssistantService: ZaraAssistantService = import.meta.env.VITE_ZARA_AI_MODE === "live"
  ? new RealZaraAssistantService()
  : new MockZaraAssistantService();
