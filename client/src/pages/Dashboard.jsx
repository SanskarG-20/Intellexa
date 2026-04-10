import { SignOutButton, useUser } from "@clerk/clerk-react";

function Dashboard() {
  const { user } = useUser();
  const name =
    user?.firstName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    "Builder";

  return (
    <section className="dashboard-page">
      <div className="dashboard-card">
        <p className="dashboard-kicker">INTELLEXA DASHBOARD</p>
        <h1 className="dashboard-title">Welcome, {name}</h1>
        <p className="dashboard-subtitle">
          You are authenticated. This is your protected workspace.
        </p>
        <SignOutButton>
          <button className="dashboard-signout" type="button">
            Sign out
          </button>
        </SignOutButton>
      </div>
    </section>
  );
}

export default Dashboard;
