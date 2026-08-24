import type {Metadata} from "next";import "./globals.css";import "./brand.css";
export const metadata:Metadata={title:"VideoSketchIt | Animated Sketch Video Studio",description:"Turn scripts and narration into animated sketch and infographic videos with AI-assisted planning and local rendering.",icons:{icon:"/brand-mark.png"}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body>{children}</body></html>}
