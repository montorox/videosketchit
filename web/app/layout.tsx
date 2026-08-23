import type {Metadata} from "next";import "./globals.css";import "./brand.css";
export const metadata:Metadata={title:"Warmth Studio Codex | Subscription-Powered Video Workshop",description:"Create narrated whiteboard and infographic videos with your ChatGPT/Codex subscription and a local rendering pipeline.",icons:{icon:"/brand-mark.png"}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body>{children}</body></html>}
