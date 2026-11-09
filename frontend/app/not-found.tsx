import Link from "next/link";
import { Footer } from "@/components/Footer";

/**
 * Shown for an unknown page, and for a record that is outside the user's scope. The API
 * answers 404 in both cases, so the page does not reveal whether the record exists.
 */
export default function NotFound() {
  return (
    <>
      <main className="landing" id="content">
        <p className="label-small">Not found</p>
        <h1>This page is not available.</h1>
        <p className="muted">It does not exist, or it is outside the jobs your role can see.</p>
        <p>
          <Link href="/dashboard" className="ff-link">
            Go to the dashboard
          </Link>
        </p>
      </main>
      <Footer />
    </>
  );
}
