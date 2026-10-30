"""Command Line Interface for the hotel scraping system."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from config.logging import setup_logging
from src.config import load_settings
from src.db.repository import HotelRepository
from src.db.session import DatabaseManager
from src.models.schemas import ExportFormat
from src.pipeline.exporter import DataExporter
from src.pipeline.runner import PipelineOrchestrator
from src.providers import get_provider

app = typer.Typer(
    name="hotel-scraper",
    help="Production-grade Google Maps Hotel Data Scraper",
    add_completion=False,
)
console = Console()


@app.callback()
def main_callback(
    config: str = typer.Option(
        "config/config.yaml", "--config", "-c", help="Path to config.yaml"
    ),
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Output logs strictly as JSON"
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
):
    """Global CLI configuration initializer."""
    setup_logging(log_level=log_level, json_format=json_logs)


@app.command("scrape")
def scrape_command(
    region: str = typer.Option(
        ..., "--region", "-r", help="Target city or region name from config.yaml"
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="Provider: 'google_maps_playwright' or 'google_places_api'",
    ),
    concurrency: int | None = typer.Option(
        None, "--concurrency", help="Worker concurrency override"
    ),
    headless: bool | None = typer.Option(
        None, "--headless/--no-headless", help="Run browser in headless mode"
    ),
):
    """Execute hotel scraping for a specified region."""
    settings = load_settings()
    if concurrency:
        settings.scraper.concurrency = concurrency
    if headless is not None:
        settings.scraper.headless = headless

    selected_provider = get_provider(settings, provider_name=provider)
    db_manager = DatabaseManager(settings.database.url, echo=settings.database.echo_sql)
    orchestrator = PipelineOrchestrator(
        settings, db_manager, provider=selected_provider
    )

    console.print(f"[bold green]Starting scrape run for region:[/bold green] {region}")
    console.print(
        f"[dim]Provider:[/dim] {provider or settings.providers.active} | [dim]Concurrency:[/dim] {settings.scraper.concurrency}"
    )

    try:
        job_id = asyncio.run(orchestrator.execute_scrape(region_name=region))
        console.print(
            f"[bold green]Scrape job {job_id} finished successfully.[/bold green]"
        )
    except KeyboardInterrupt:
        console.print(
            "[yellow]Scrape interrupted by user. State is saved and can be resumed with 'resume'.[/yellow]"
        )
    except Exception as e:
        console.print(f"[bold red]Scrape run failed:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command("resume")
def resume_command(
    job_id: str | None = typer.Option(
        None, "--job-id", "-j", help="Specific Job Run ID to resume"
    ),
    region: str | None = typer.Option(
        None, "--region", "-r", help="Find latest incomplete job for region"
    ),
):
    """Resume an interrupted or paused scraping run."""
    settings = load_settings()
    db_manager = DatabaseManager(settings.database.url)

    async def _resolve_and_resume():
        await db_manager.create_tables()
        target_job_id = job_id
        target_region = region

        if not target_job_id:
            async with db_manager.session() as session:
                repo = HotelRepository(session)
                latest = await repo.get_latest_resumable_job(region=region)
                if not latest:
                    console.print(
                        "[yellow]No incomplete or resumable scraping jobs found.[/yellow]"
                    )
                    return
                target_job_id = latest.id
                target_region = latest.region

        console.print(
            f"[bold cyan]Resuming job:[/bold cyan] {target_job_id} ({target_region})"
        )
        selected_provider = get_provider(settings)
        orchestrator = PipelineOrchestrator(
            settings, db_manager, provider=selected_provider
        )
        await orchestrator.execute_scrape(
            region_name=target_region, resume_job_id=target_job_id
        )
        console.print(
            f"[bold green]Resumed job {target_job_id} completed.[/bold green]"
        )

    try:
        asyncio.run(_resolve_and_resume())
    except KeyboardInterrupt:
        console.print(
            "[yellow]Resumed job interrupted. Run state safely preserved.[/yellow]"
        )
    except Exception as e:
        console.print(f"[bold red]Resume error:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command("export")
def export_command(
    fmt: ExportFormat = typer.Option(
        ExportFormat.CSV, "--format", "-f", help="Target format: csv or json"
    ),
    city: str | None = typer.Option(
        None, "--city", help="Filter export by city substring"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Custom output file destination path"
    ),
):
    """Export collected hotel records from the database to CSV or JSON."""
    settings = load_settings()
    db_manager = DatabaseManager(settings.database.url)
    exporter = DataExporter(db_manager, export_dir=settings.app.export_dir)

    async def _do_export():
        path = await exporter.export_data(fmt=fmt, city=city, output_file=output)
        console.print(
            f"[bold green]Data exported successfully to:[/bold green] {path.resolve()}"
        )

    try:
        asyncio.run(_do_export())
    except Exception as e:
        console.print(f"[bold red]Export error:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command("status")
def status_command():
    """Display recent job runs, hotel count, and scraping metrics."""
    settings = load_settings()
    db_manager = DatabaseManager(settings.database.url)

    async def _show_status():
        await db_manager.create_tables()
        async with db_manager.session() as session:
            from sqlalchemy import func, select

            from src.models.entities import Hotel, JobRun

            hotel_count = (
                await session.execute(select(func.count(Hotel.place_id)))
            ).scalar() or 0
            runs = (
                (
                    await session.execute(
                        select(JobRun).order_by(JobRun.started_at.desc()).limit(10)
                    )
                )
                .scalars()
                .all()
            )

        console.print(
            f"\n[bold]Total Unique Hotels in DB:[/bold] [cyan]{hotel_count}[/cyan]\n"
        )

        table = Table(title="Recent Scraping Jobs")
        table.add_column("Job ID", style="cyan")
        table.add_column("Region", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Candidates", justify="right")
        table.add_column("Completed", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Started At", style="dim")

        for r in runs:
            table.add_row(
                r.id,
                r.region,
                r.status,
                str(r.total_candidates),
                str(r.completed_count),
                str(r.failed_count),
                r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else "",
            )
        console.print(table)

    asyncio.run(_show_status())


@app.command("list-cities")
def list_cities_command(
    state: str | None = typer.Option(None, "--state", "-s", help="Filter cities by State/UT"),
    tier: str | None = typer.Option(None, "--tier", "-t", help="Filter by Tier (e.g. 'Tier 1 Metro', 'Hill Station')"),
    search: str | None = typer.Option(None, "--search", "-q", help="Search city name substring"),
):
    """List supported Indian cities, states, and their database scrape status."""
    import json
    from pathlib import Path
    cities_file = Path("data/india_cities.json")
    if not cities_file.exists():
        console.print("[red]data/india_cities.json not found.[/red]")
        raise typer.Exit(code=1)

    cities = json.load(open(cities_file, encoding="utf-8"))

    if state:
        cities = [c for c in cities if state.lower() in c.get("state", "").lower()]
    if tier:
        cities = [c for c in cities if tier.lower() in c.get("tier", "").lower()]
    if search:
        cities = [c for c in cities if search.lower() in c.get("name", "").lower()]

    # Check which cities are already in DB
    settings = load_settings()
    db_manager = DatabaseManager(settings.database.url)

    async def _get_db_cities():
        await db_manager.create_tables()
        async with db_manager.session() as session:
            from sqlalchemy import select
            from src.models.entities import Hotel
            rows = (await session.execute(select(Hotel.city).distinct())).all()
            return {r[0].lower() for r in rows if r[0]}

    scraped_cities = asyncio.run(_get_db_cities())

    table = Table(title=f"Indian Cities & Tourism Destinations ({len(cities)} found)")
    table.add_column("City Name", style="bold cyan")
    table.add_column("State / UT", style="magenta")
    table.add_column("Classification / Tier", style="green")
    table.add_column("Coordinates (Lat, Lng)", style="dim")
    table.add_column("DB Status", justify="center")

    for c in cities:
        c_name = c["name"]
        in_db = any(c_name.lower() in sc for sc in scraped_cities)
        status_label = "[bold green]Scraped[/bold green]" if in_db else "[dim yellow]Pending[/dim yellow]"
        coords = f"{c.get('lat', 0.0):.2f}, {c.get('lng', 0.0):.2f}"
        table.add_row(c_name, c.get("state", ""), c.get("tier", ""), coords, status_label)

    console.print(table)


@app.command("scrape-india")
def scrape_india_command(
    state: str | None = typer.Option(None, "--state", "-s", help="Batch scrape all cities in this State"),
    tier: str | None = typer.Option(None, "--tier", "-t", help="Batch scrape all cities in this Tier"),
    limit: int = typer.Option(5, "--limit", "-l", help="Maximum number of cities to scrape in this batch"),
    concurrency: int | None = typer.Option(None, "--concurrency", help="Worker concurrency override"),
    headless: bool | None = typer.Option(None, "--headless/--no-headless", help="Run browser in headless mode"),
):
    """Batch scrape hotel data across multiple cities in India."""
    import json
    from pathlib import Path
    cities_file = Path("data/india_cities.json")
    if not cities_file.exists():
        console.print("[red]data/india_cities.json not found.[/red]")
        raise typer.Exit(code=1)

    all_cities = json.load(open(cities_file, encoding="utf-8"))
    targets = all_cities

    if state:
        targets = [c for c in targets if state.lower() in c.get("state", "").lower()]
    if tier:
        targets = [c for c in targets if tier.lower() in c.get("tier", "").lower()]

    targets = targets[:limit]
    if not targets:
        console.print("[yellow]No cities matched your filter criteria.[/yellow]")
        return

    console.print(f"[bold green]Starting India Batch Scrape for {len(targets)} cities:[/bold green]")
    for i, c in enumerate(targets, 1):
        console.print(f" {i}. [bold cyan]{c['name']}[/bold cyan] ({c.get('state', '')}) - [dim]{c.get('tier', '')}[/dim]")

    settings = load_settings()
    if concurrency:
        settings.scraper.concurrency = concurrency
    if headless is not None:
        settings.scraper.headless = headless

    db_manager = DatabaseManager(settings.database.url, echo=settings.database.echo_sql)
    provider = get_provider(settings)
    orchestrator = PipelineOrchestrator(settings, db_manager, provider=provider)

    async def _run_batch():
        for c in targets:
            city_name = c["name"]
            console.print(f"\n[bold yellow]>>> Processing City: {city_name} ({c.get('state', '')})[/bold yellow]")
            try:
                job_id = await orchestrator.execute_scrape(region_name=city_name)
                console.print(f"[bold green][OK] Completed city {city_name} (Job: {job_id})[/bold green]")
            except Exception as e:
                console.print(f"[bold red][FAIL] Failed city {city_name}: {e}[/bold red]")

    try:
        asyncio.run(_run_batch())
        console.print("\n[bold green]India Batch Scrape Completed Successfully.[/bold green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]India batch scrape paused by user. Progress is saved in DB.[/yellow]")


if __name__ == "__main__":
    app()
