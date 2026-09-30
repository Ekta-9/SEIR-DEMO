from datetime import datetime, timezone

import pytest

from app.collectors.config_files import (
    ComponentResolver,
    ConfigCategory,
    ReferenceKind,
    Resolution,
    RawToken,
    build_config_evidence,
    classify_config_path,
    default_bean_name,
    scan_revision,
    scan_text,
)
from tests.git_repo_builder import GitRepoBuilder, java

PET = "org.springframework.samples.petclinic"


# ---- classification ----------------------------------------------------------------

@pytest.mark.parametrize(("path", "expected"), [
    ("src/main/resources/application.properties", ConfigCategory.RUNTIME),
    ("svc/src/main/resources/application.yml", ConfigCategory.RUNTIME),
    ("src/main/resources/spring/business-config.xml", ConfigCategory.RUNTIME),
    ("src/main/resources/META-INF/services/com.acme.Plugin", ConfigCategory.RUNTIME),
    ("src/main/resources/META-INF/spring.factories", ConfigCategory.RUNTIME),
    ("src/test/resources/application-test.yml", ConfigCategory.TEST),
    ("pom.xml", ConfigCategory.BUILD),
    ("build.gradle", ConfigCategory.BUILD),
    ("settings.gradle.kts", ConfigCategory.BUILD),
    ("src/conf/spotbugs-exclude-filter.xml", ConfigCategory.BUILD),
    ("src/site/xdoc/index.xml", None),  # documentation
    ("src/changes/changes.xml", None),  # release notes
    ("src/main/resources/messages/messages_de.properties", None),  # i18n text
    (".github/workflows/ci.yml", None),
    ("docker-compose.yml", None),
    ("k8s/petclinic.yml", None),
    ("src/main/java/com/acme/Foo.java", None),
    ("script.kts", None),
    # found in 20 years of commons-lang / commons-io / petclinic history:
    ("xdocs/upgradeto2_0.xml", None),  # Maven 1 documentation
    ("LANG_2_2_RC1/xdocs/index.xml", None),
    ("build.xml", ConfigCategory.BUILD),  # Ant
    ("maven.xml", ConfigCategory.BUILD),  # Maven 1
    ("project.xml", ConfigCategory.BUILD),
    ("project.properties", ConfigCategory.BUILD),
    ("sb-excludes.xml", ConfigCategory.BUILD),
    ("sonar-project.properties", ConfigCategory.BUILD),
    (".settings/org.eclipse.wst.common.project.facet.core.xml", None),  # IDE settings
    (".tanzu/config/spring-petclinic.yml", None),  # deployment tooling
    ("travis.yml", None),
    ("db/petclinic_tomcat_all.xml", None),
    ("config/application-prod.yml", ConfigCategory.RUNTIME),  # Spring Boot config outside resources
    ("src/main/webapp/WEB-INF/web.xml", ConfigCategory.RUNTIME),
])
def test_classify(path, expected):
    assert classify_config_path(path) == expected


# ---- scanning ---------------------------------------------------------------------------

def test_scan_spring_xml():
    xml = "\n".join([
        "<beans>",
        f'  <!-- <bean class="{PET}.web.Commented"/> -->',
        f'  <bean id="callMonitor" class="{PET}.util.CallMonitoringAspect"/>',
        f'  <oxm:class-to-be-bound name="{PET}.model.Vets"/>',
        '  <property name="cacheManager" ref="ehcache"/>',
        '  <bean p:dataSource-ref="dataSource"/>',
        "</beans>",
    ])
    tokens = {(t.text, t.line, t.kind) for t in scan_text("src/main/resources/spring/tools-config.xml", xml)}
    assert tokens == {
        (f"{PET}.util.CallMonitoringAspect", 3, ReferenceKind.CLASS_NAME),
        (f"{PET}.model.Vets", 4, ReferenceKind.CLASS_NAME),
        ("ehcache", 5, ReferenceKind.BEAN_REFERENCE),
        ("dataSource", 6, ReferenceKind.BEAN_REFERENCE),
    }  # the commented-out bean is ignored, and line numbers survive comment removal


def test_scan_properties_and_yaml_comments():
    props = "# spring.main.sources=com.acme.Old\nspring.jpa.naming=org.hibernate.Naming\nlogging.level.org.springframework=INFO\n"
    assert [t.text for t in scan_text("application.properties", props)] == ["org.hibernate.Naming"]  # no packages
    yaml = "app:\n  handler: com.acme.Handler  # was com.acme.OldHandler\n"
    assert [(t.text, t.line) for t in scan_text("application.yml", yaml)] == [("com.acme.Handler", 2)]


def test_scan_service_loader_and_auto_configuration():
    service = scan_text("src/main/resources/META-INF/services/com.acme.spi.Plugin", "com.acme.impl.FastPlugin\n")
    assert {(t.text, t.kind) for t in service} == {
        ("com.acme.spi.Plugin", ReferenceKind.SERVICE_INTERFACE),
        ("com.acme.impl.FastPlugin", ReferenceKind.SERVICE_LOADER),
    }
    factories = "org.springframework.boot.autoconfigure.EnableAutoConfiguration=\\\n  com.acme.AutoConfig,\\\n  com.acme.OtherConfig\n"
    kinds = {(t.text, t.kind) for t in scan_text("src/main/resources/META-INF/spring.factories", factories)}
    assert ("com.acme.AutoConfig", ReferenceKind.AUTO_CONFIGURATION) in kinds
    assert ("com.acme.OtherConfig", ReferenceKind.AUTO_CONFIGURATION) in kinds


# ---- resolution ---------------------------------------------------------------------------

def token(text: str, kind=ReferenceKind.CLASS_NAME) -> RawToken:
    return RawToken(text, 1, kind, "")


@pytest.fixture
def resolver() -> ComponentResolver:
    return ComponentResolver(
        [f"{PET}.owner.OwnerRepository", f"{PET}.util.CallMonitoringAspect", "com.a.Clash", "com.b.Clash"],
        known_packages=[f"{PET}.web"],  # a package whose classes were deleted
    )


@pytest.mark.parametrize(("text", "expected"), [
    (f"{PET}.util.CallMonitoringAspect", (Resolution.RESOLVED, f"{PET}.util.CallMonitoringAspect")),
    (f"{PET}.util.CallMonitoringAspect$Inner", (Resolution.RESOLVED, f"{PET}.util.CallMonitoringAspect")),
    (f"{PET}.util.CallMonitoringAspect.Inner", (Resolution.RESOLVED, f"{PET}.util.CallMonitoringAspect")),
    (f"{PET}.web.VetsAtomView", (Resolution.UNRESOLVED, None)),  # deleted class: possibly stale config
    (f"{PET}.owner.Missing", (Resolution.UNRESOLVED, None)),
    ("org.hibernate.boot.model.naming.Strategy", (Resolution.EXTERNAL, None)),
])
def test_resolve_class_names(resolver, text, expected):
    assert resolver.resolve(token(text)) == expected


def test_resolve_bean_names(resolver):
    assert resolver.resolve(token("ownerRepository", ReferenceKind.BEAN_REFERENCE)) == (
        Resolution.RESOLVED, f"{PET}.owner.OwnerRepository")
    assert resolver.resolve(token("clash", ReferenceKind.BEAN_REFERENCE)) == (Resolution.EXTERNAL, None)  # ambiguous
    assert resolver.resolve(token("dataSource", ReferenceKind.BEAN_REFERENCE)) == (Resolution.EXTERNAL, None)


def test_default_bean_name():
    assert default_bean_name("OwnerRepository") == "ownerRepository"
    assert default_bean_name("URLHandler") == "URLHandler"  # Introspector keeps leading acronyms


# ---- end to end on a real git repository ---------------------------------------------------

def test_scan_revision_and_evidence(tmp_path):
    repo = GitRepoBuilder(tmp_path / "repo")
    repo.write("src/main/java/com/acme/Handler.java", java("com.acme", "Handler"))
    repo.write("src/main/resources/app.xml",
               '<beans>\n  <bean class="com.acme.Handler"/>\n  <bean class="com.acme.Handler"/>\n</beans>\n')
    repo.write("src/test/resources/test.yml", "handler: com.acme.Handler\n")
    repo.write("src/site/xdoc/index.xml", "<p>See com.acme.Handler</p>\n")  # docs: ignored
    old = repo.commit("add", datetime(2024, 1, 1, tzinfo=timezone.utc))
    repo.write("src/main/resources/app.xml", "<beans/>\n")
    new = repo.commit("remove bean", datetime(2024, 2, 1, tzinfo=timezone.utc))

    resolver = ComponentResolver(["com.acme.Handler"])
    before = scan_revision(repo.path, old, resolver)
    after = scan_revision(repo.path, new, resolver)
    assert len(before.resolved()) == 3 and len(after.resolved()) == 1  # historical revision read from git

    as_of = datetime(2024, 1, 2, tzinfo=timezone.utc)
    items = build_config_evidence(before, ["com.acme.Handler"], "acme/shop", old, as_of)
    refs = [i for i in items if i.evidence_type == "config_reference"]
    [count] = [i for i in items if i.evidence_type == "config_reference_count"]
    assert len({i.evidence_id for i in refs}) == len(refs) == 3  # unique IDs per location
    assert count.value == 2  # only RUNTIME references are counted, not TEST
    assert {i.value for i in refs} == {"RUNTIME", "TEST"}
